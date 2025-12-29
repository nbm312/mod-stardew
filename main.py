import os
import discord
from discord.ext import commands
from discord import app_commands
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
import requests

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- GOOGLE SHEETS ----------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")
creds_dict = json.loads(creds_json)

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)

SHEET_NAME = "MODS STARDEW"
sheet = client.open(SHEET_NAME).worksheet("MODS")

HEADERS = [
    "Nombre",
    "Categoría",
    "Descripción",
    "Prioridad",
    "Dependencias",
    "Alternativa",
    "Instalado",
    "Link"
]

# ---------------- CONSTANTES ----------------
PRIORIDADES = ["Alta", "Media", "Baja", "Vetada", "Evaluar"]
ALTERNATIVAS = ["Sí", "No"]
INSTALADO_VALORES = ["TRUE", "FALSE"]  # Para checkbox
NEXUS_API_KEY = os.getenv("DISCORD_NEXUS_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")

if not NEXUS_API_KEY:
    print("❌ No se encontró NEXUS_API_KEY en variables de entorno")
if not TOKEN:
    print("❌ No se encontró DISCORD_TOKEN en variables de entorno")

# ---------------- HELP ----------------
HELP_TEXT = """
📌 **Comandos disponibles**:

/listmods [page]  
- Muestra los mods paginados (10 por página).

/mods [categoria] [page]  
- Muestra mods filtrados por categoría. Si no se indica categoría, muestra resumen por categorías.

/mods_prioridad prioridad [page]  
- Filtra mods por prioridad (Alta, Media, Baja, Vetada, Evaluar).

/mods_instalado instalado [page]  
- Filtra mods por si están instalados: "sí" o "no".

/mods_alternativa alternativa [page]  
- Filtra mods por si tienen alternativa: "Sí" o "No".

/search texto [page]  
- Busca mods cuyo nombre o descripción contenga el texto dado.

/addmod mod_id [prioridad] [alternativa] [instalado]  
- Añade un mod usando NexusMods API. Se puede indicar prioridad, alternativa y si está instalado.

/updatefield fila campo valor  
- Actualiza un campo concreto de una fila.
"""

# ---------------- UTILIDADES ----------------
def get_fila_vacia():
    columna_nombre = sheet.col_values(1)
    for i, valor in enumerate(columna_nombre, start=1):
        if not valor.strip():
            return i
    return len(columna_nombre) + 1

def normalizar_instalado(valor: str):
    if valor.lower() in ["si", "sí", "true", "verdadero"]:
        return "TRUE"
    return "FALSE"
# ---------------- AUTOCOMPLETADO CORRECTO ----------------

# Para prioridad
async def prioridad_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=p, value=p) for p in PRIORIDADES if current.lower() in p.lower()]

# Para alternativa
async def alternativa_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=a, value=a) for a in ALTERNATIVAS if current.lower() in a.lower()]

# Para instalado
async def instalado_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=i, value=i) for i in ["Sí","No"] if current.lower() in i.lower()]

# Para campo
async def campo_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=h, value=h) for h in HEADERS if current.lower() in h.lower()]


# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot listo y comandos sincronizados como {bot.user}")

# ---------------- HELP ----------------
@bot.tree.command(name="help", description="Muestra los comandos disponibles")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(HELP_TEXT, ephemeral=True)

# ---------------- LIST MODS ----------------
@bot.tree.command(name="listmods", description="Muestra mods paginados")
@app_commands.describe(page="Número de página")
async def listmods(interaction: discord.Interaction, page: int = 1):
    try:
        rows = sheet.get_all_records()
        if not rows:
            await interaction.response.send_message("❌ No hay mods registrados.")
            return

        PER_PAGE = 10
        total = len(rows)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"❌ Página inválida. Usa una entre 1 y {total_pages}.")
            return

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = rows[start:end]

        msg = f"📋 **Mods — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            categoria = row["Categoría"]
            instalado = "✅" if str(row["Instalado"]).lower() in ["true","sí","si"] else "❌"
            msg += f"{i}. **{nombre}** — {categoria} — {instalado}\n"
        msg += f"\n_Mostrando {start + 1}–{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)
    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- MODS POR CATEGORÍA ----------------
@bot.tree.command(name="mods", description="Filtra mods por categoría")
@app_commands.describe(categoria="Categoría de mod", page="Número de página")
async def mods(interaction: discord.Interaction, categoria: str = None, page: int = 1):
    try:
        rows = sheet.get_all_records()
        if not rows:
            await interaction.response.send_message("❌ No hay mods registrados.")
            return

        if categoria is None:
            # Resumen
            resumen = {}
            for row in rows:
                cat = row["Categoría"] or "-"
                resumen[cat] = resumen.get(cat, 0) + 1
            msg = "📊 **Recuento de mods por categoría:**\n"
            for cat, count in resumen.items():
                msg += f"- {cat}: {count}\n"
            await interaction.response.send_message(msg)
            return

        filtered = [r for r in rows if str(r["Categoría"]).lower() == categoria.lower()]
        if not filtered:
            await interaction.response.send_message(f"❌ No hay mods en la categoría '{categoria}'.")
            return

        PER_PAGE = 10
        total = len(filtered)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"❌ Página inválida. Usa una entre 1 y {total_pages}.")
            return

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = filtered[start:end]

        msg = f"📋 **Mods — Categoría: {categoria} — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            instalado = "✅" if str(row["Instalado"]).lower() in ["true","sí","si"] else "❌"
            msg += f"{i}. **{nombre}** — {instalado}\n"
        msg += f"\n_Mostrando {start + 1}-{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)

    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- MODS POR PRIORIDAD ----------------
@bot.tree.command(name="mods_prioridad", description="Filtra mods por prioridad")
@app_commands.describe(prioridad="Prioridad del mod", page="Número de página")
@app_commands.autocomplete(prioridad=prioridad_autocomplete)
async def mods_prioridad(interaction: discord.Interaction, prioridad: str, page: int = 1):
    try:
        rows = sheet.get_all_records()
        filtered = [r for r in rows if str(r["Prioridad"]).lower() == prioridad.lower()]
        if not filtered:
            await interaction.response.send_message(f"❌ No hay mods con prioridad '{prioridad}'.")
            return

        PER_PAGE = 10
        total = len(filtered)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"❌ Página inválida. Usa una entre 1 y {total_pages}.")
            return

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = filtered[start:end]

        msg = f"📋 **Mods — Prioridad: {prioridad} — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            categoria = row["Categoría"]
            instalado = "✅" if str(row["Instalado"]).lower() in ["true","sí","si"] else "❌"
            msg += f"{i}. **{nombre}** — {categoria} — {instalado}\n"
        msg += f"\n_Mostrando {start + 1}-{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)
    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- MODS POR INSTALADO ----------------
@bot.tree.command(name="mods_instalado", description="Filtra mods por si están instalados")
@app_commands.describe(instalado="Sí o No", page="Número de página")
@app_commands.autocomplete(instalado=instalado_autocomplete)
async def mods_instalado(interaction: discord.Interaction, instalado: str, page: int = 1):
    try:
        rows = sheet.get_all_records()
        if instalado.lower() in ["sí","si"]:
            filtered = [r for r in rows if str(r["Instalado"]).upper() == "TRUE"]
        else:
            filtered = [r for r in rows if str(r["Instalado"]).upper() == "FALSE"]

        if not filtered:
            await interaction.response.send_message(f"❌ No hay mods con instalado = '{instalado}'.")
            return

        PER_PAGE = 10
        total = len(filtered)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"❌ Página inválida. Usa una entre 1 y {total_pages}.")
            return

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = filtered[start:end]

        msg = f"📋 **Mods — Instalado: {instalado} — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            categoria = row["Categoría"]
            prioridad = row["Prioridad"]
            msg += f"{i}. **{nombre}** — {categoria} — {prioridad}\n"
        msg += f"\n_Mostrando {start + 1}-{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)

    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- MODS POR ALTERNATIVA ----------------
@bot.tree.command(name="mods_alternativa", description="Filtra mods por alternativa")
@app_commands.describe(alternativa="Sí o No", page="Número de página")
@app_commands.autocomplete(alternativa=alternativa_autocomplete)
async def mods_alternativa(interaction: discord.Interaction, alternativa: str, page: int = 1):
    try:
        rows = sheet.get_all_records()
        filtered = [r for r in rows if str(r["Alternativa"]).lower() == alternativa.lower()]
        if not filtered:
            await interaction.response.send_message(f"❌ No hay mods con alternativa = '{alternativa}'.")
            return

        PER_PAGE = 10
        total = len(filtered)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = filtered[start:end]

        msg = f"📋 **Mods — Alternativa: {alternativa} — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            categoria = row["Categoría"]
            prioridad = row["Prioridad"]
            msg += f"{i}. **{nombre}** — {categoria} — {prioridad}\n"
        msg += f"\n_Mostrando {start + 1}-{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)

    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- SEARCH ----------------
@bot.tree.command(name="search", description="Busca mods por texto")
@app_commands.describe(texto="Texto a buscar en nombre o descripción", page="Número de página")
async def search(interaction: discord.Interaction, texto: str, page: int = 1):
    try:
        rows = sheet.get_all_records()
        filtered = [r for r in rows if texto.lower() in str(r["Nombre"]).lower() or texto.lower() in str(r["Descripción"]).lower()]
        if not filtered:
            await interaction.response.send_message(f"❌ No se encontraron mods que contengan '{texto}'.")
            return

        PER_PAGE = 10
        total = len(filtered)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE

        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        page_rows = filtered[start:end]

        msg = f"🔍 **Mods — Búsqueda: '{texto}' — Página {page}/{total_pages}**\n\n"
        for i, row in enumerate(page_rows, start=start + 1):
            nombre = row["Nombre"]
            categoria = row["Categoría"]
            prioridad = row["Prioridad"]
            msg += f"{i}. **{nombre}** — {categoria} — {prioridad}\n"
        msg += f"\n_Mostrando {start + 1}-{min(end, total)} de {total}_"
        await interaction.response.send_message(msg)

    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error: {e}")

# ---------------- ADD MOD ----------------
@bot.tree.command(name="addmod", description="Añade un mod usando NexusMods API")
@app_commands.describe(mod_id="ID del mod en NexusMods",
                       prioridad="Prioridad del mod",
                       alternativa="Si tiene alternativa",
                       instalado="Si está instalado")
@app_commands.autocomplete(prioridad=prioridad_autocomplete)
@app_commands.autocomplete(alternativa=alternativa_autocomplete)
@app_commands.autocomplete(instalado=instalado_autocomplete)
async def addmod(interaction: discord.Interaction, mod_id: int, prioridad: str = "Media",
                 alternativa: str = "No", instalado: str = "no"):
    try:
        if not NEXUS_API_KEY:
            await interaction.response.send_message("❌ API Key de NexusMods no configurada.")
            return

        url = f"https://api.nexusmods.com/v1/games/stardewvalley/mods/{mod_id}.json"
        headers = {"apikey": NEXUS_API_KEY, "Accept": "application/json"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            await interaction.response.send_message(f"❌ Error al acceder a la API: {response.status_code}")
            return

        data = response.json()
        nombre = data.get("name", "Mod desconocido")
        descripcion = data.get("summary", "Sin descripción")
        link = f"https://www.nexusmods.com/stardewvalley/mods/{mod_id}"

        prioridad = prioridad if prioridad in PRIORIDADES else "Media"
        alternativa = alternativa if alternativa in ALTERNATIVAS else "No"
        instalado_val = normalizar_instalado(instalado)

        new_row = [nombre, "-", descripcion, prioridad, "", alternativa, instalado_val, link]
        fila_vacia = get_fila_vacia()
        sheet.update(f"A{fila_vacia}:H{fila_vacia}", [new_row])

        await interaction.response.send_message(f"✅ Mod añadido: **{nombre}**")
    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error al añadir el mod: {e}")

# ---------------- UPDATE FIELD ----------------
@bot.tree.command(name="updatefield", description="Actualiza un campo concreto de una fila")
@app_commands.describe(fila="Número de fila a actualizar", campo="Nombre del campo", valor="Nuevo valor")
@app_commands.autocomplete(campo=campo_autocomplete)
async def updatefield(interaction: discord.Interaction, fila: int, campo: str, valor: str):
    try:
        campo = campo.capitalize()
        if campo not in HEADERS:
            await interaction.response.send_message(f"❌ Campo inválido. Debe ser uno de: {', '.join(HEADERS)}")
            return
        col_index = HEADERS.index(campo) + 1

        if campo == "Instalado":
            valor = normalizar_instalado(valor)

        sheet.update_cell(fila, col_index, valor)
        await interaction.response.send_message(f"✅ Fila {fila} actualizada: {campo} = {valor}")
    except Exception as e:
        print(f"[ERROR] {e}")
        await interaction.response.send_message(f"❌ Ocurrió un error al actualizar la fila: {e}")

# ---------------- RUN ----------------
bot.run(TOKEN)
