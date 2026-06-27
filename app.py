from flask import Flask, render_template, request
import imaplib
import email
from email.header import decode_header
import json
import socket
import re
from html import unescape

app = Flask(__name__)

socket.setdefaulttimeout(12)

with open("cuentas.json", "r", encoding="utf-8") as f:
    cuentas = json.load(f)


def decodificar(texto):
    if not texto:
        return ""

    resultado = ""

    for parte, codificacion in decode_header(texto):
        if isinstance(parte, bytes):
            try:
                resultado += parte.decode(codificacion or "utf-8", errors="ignore")
            except:
                resultado += parte.decode("utf-8", errors="ignore")
        else:
            resultado += parte

    return resultado


def limpiar_html(html):
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n", html, flags=re.I)
    html = re.sub(r"<.*?>", "", html)
    html = unescape(html)
    html = re.sub(r"\n\s*\n\s*\n+", "\n\n", html)
    return html.strip()


def obtener_contenido(mensaje):
    contenido_texto = ""
    contenido_html = ""

    if mensaje.is_multipart():
        for parte in mensaje.walk():
            tipo = parte.get_content_type()
            dispo = str(parte.get("Content-Disposition"))

            if "attachment" in dispo:
                continue

            try:
                payload = parte.get_payload(decode=True)
                if not payload:
                    continue

                charset = parte.get_content_charset() or "utf-8"
                texto = payload.decode(charset, errors="ignore")

                if tipo == "text/plain" and texto.strip():
                    contenido_texto = texto.strip()
                    break

                if tipo == "text/html" and texto.strip():
                    contenido_html = texto

            except:
                continue
    else:
        try:
            payload = mensaje.get_payload(decode=True)
            charset = mensaje.get_content_charset() or "utf-8"
            texto = payload.decode(charset, errors="ignore")

            if mensaje.get_content_type() == "text/html":
                contenido_html = texto
            else:
                contenido_texto = texto
        except:
            pass

    if contenido_texto:
        return contenido_texto

    if contenido_html:
        return limpiar_html(contenido_html)

    return "(Este correo no tiene contenido visible o viene en un formato no compatible.)"


@app.route("/", methods=["GET", "POST"])
def index():
    resultados = []

    correo_seleccionado = "todos"
    palabra = ""
    limite = 10
    errores = []

    if request.method == "POST":
        palabra = request.form.get("palabra", "").lower().strip()
        correo_seleccionado = request.form.get("correo", "todos")
        limite = int(request.form.get("limite", 10))

        contador = 0

        for cuenta in cuentas:
            if correo_seleccionado != "todos" and cuenta["email"] != correo_seleccionado:
                continue

            mail = None

            try:
                mail = imaplib.IMAP4_SSL(cuenta["imap"], timeout=12)
                mail.login(cuenta["email"], cuenta["password"])

                try:
                    mail.select("INBOX")
                except:
                    mail.select('"[Gmail]/All Mail"')

                estado, datos = mail.search(None, "ALL")

                if estado != "OK" or not datos or not datos[0]:
                    continue

                ids = datos[0].split()[::-1][:limite]

                for num in ids:
                    try:
                        estado, data = mail.fetch(num, "(RFC822)")

                        if estado != "OK" or not data or not data[0]:
                            continue

                        mensaje = email.message_from_bytes(data[0][1])

                        asunto = decodificar(mensaje.get("Subject", ""))
                        remitente = decodificar(mensaje.get("From", ""))
                        fecha = mensaje.get("Date", "")

                        contenido = obtener_contenido(mensaje)

                        texto_busqueda = (
                            asunto.lower()
                            + " "
                            + remitente.lower()
                            + " "
                            + contenido.lower()
                        )

                        if palabra and palabra not in texto_busqueda:
                            continue

                        contador += 1

                        resultados.append({
                            "id": contador,
                            "cuenta": cuenta["email"],
                            "asunto": asunto or "(Sin asunto)",
                            "de": remitente or "(Desconocido)",
                            "fecha": fecha or "(Sin fecha)",
                            "contenido": contenido[:15000]
                        })

                    except Exception as e:
                        print("Error leyendo correo:", e)
                        continue

                mail.logout()

            except Exception as e:
                errores.append(f"{cuenta['email']}: {e}")
                print("ERROR CUENTA:", cuenta["email"], e)

                try:
                    if mail:
                        mail.logout()
                except:
                    pass

    return render_template(
        "index.html",
        cuentas=cuentas,
        resultados=resultados,
        correo_seleccionado=correo_seleccionado,
        palabra=palabra,
        limite=limite,
        errores=errores
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)