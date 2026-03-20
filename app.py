#SUPABASE_URL = "https://olgjkmkeccjuzmppplex.supabase.co"
#SUPABASE_KEY = "sb_publishable_v8OAxCCqGM6lwtlHHl5_YA_bu2t9MIR"

# ==========================================
# 1. IMPORTACIÓN DE LIBRERÍAS
# ==========================================
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from functools import wraps
import qrcode
import io
import base64
from io import BytesIO
from xhtml2pdf import pisa
from flask import make_response
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication # Para adjuntar el PDF
from datetime import datetime

# ==========================================
# 2. INICIALIZACIÓN DE LA APLICACIÓN
# ==========================================
app = Flask(__name__)
app.secret_key = 'sb_publishable_v8OAxCCqGM6lwtlHHl5_YA_bu2t9MIR' 

# ==========================================
# 3. CONFIGURACIÓN DE SUPABASE
# ==========================================
SUPABASE_URL = "https://olgjkmkeccjuzmppplex.supabase.co"
SUPABASE_KEY = "sb_publishable_v8OAxCCqGM6lwtlHHl5_YA_bu2t9MIR"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 4. RUTAS DE AUTENTICACIÓN Y RECUPERACIÓN (TU CÓDIGO ORIGINAL)
# ==========================================

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr
# Decorador para proteger rutas privadas
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debe iniciar sesión para acceder a este módulo.")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email_input = request.form.get('email')
    password_input = request.form.get('password')
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email_input,
            "password": password_input
        })
        if auth_response.user:
            user_profile = supabase.table("perfiles")\
                .select("nombres, apellidos")\
                .eq("id", auth_response.user.id)\
                .single().execute()
            
            session['user_id'] = auth_response.user.id
            session['nombre'] = f"{user_profile.data['nombres']} {user_profile.data['apellidos']}"
            return redirect(url_for('dashboard'))
    except Exception as e:
        flash("Credenciales incorrectas. Verifique su correo y contraseña.")
        print(f"Error de Login: {e}")
    return redirect(url_for('index'))

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        cedula = request.form.get('cedula')
        nombres = request.form.get('nombres')
        apellidos = request.form.get('apellidos')
        email = request.form.get('email')
        password = request.form.get('password')
        grado = request.form.get('grado')
        try:
            auth_response = supabase.auth.sign_up({"email": email, "password": password})
            if auth_response.user:
                nuevo_perfil = {
                    "id": auth_response.user.id,
                    "cedula": cedula,
                    "nombres": nombres,
                    "apellidos": apellidos,
                    "correo_institucional": email,
                    "grado_policial": grado
                }
                supabase.table("perfiles").insert(nuevo_perfil).execute()
                flash("Registro exitoso. Inicie sesión.")
                return redirect(url_for('index'))
        except Exception as e:
            flash("Error al registrar.")
            print(e)
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    supabase.auth.sign_out()
    return redirect(url_for('index'))

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form.get('email')
        try:
            supabase.auth.reset_password_email(email, options={"redirect_to": "http://127.0.0.1:5000/restablecer"})
            flash("Enlace enviado.")
            return redirect(url_for('index'))
        except Exception as e:
            flash("Error.")
    return render_template('recuperar.html')

@app.route('/restablecer', methods=['GET', 'POST'])
def restablecer():
    if request.method == 'POST':
        nueva_password = request.form.get('password')
        try:
            supabase.auth.update_user({"password": nueva_password})
            supabase.auth.sign_out()
            session.clear()
            flash("Contraseña actualizada.")
            return redirect(url_for('index'))
        except Exception as e:
            flash("Error.")
    return render_template('restablecer.html')

# ==========================================
# 5. RUTAS DEL SISTEMA (DASHBOARD Y ACTAS INTEGRADO)
# ==========================================

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    try:
        actas_query = supabase.table("actas")\
            .select("id, titulo, fecha_reunion, lugar, estado")\
            .eq("anfitrion_id", session['user_id'])\
            .order("creado_at", desc=True).execute()
        actas_data = actas_query.data
    except Exception as e:
        actas_data = []
        print(e)
    return render_template('dashboard.html', actas=actas_data, nombre=session['nombre'])

@app.route('/nueva_acta', methods=['GET', 'POST'])
def nueva_acta():
    if 'user_id' not in session: return redirect(url_for('index'))

    if request.method == 'POST':
        # --- A. Datos del Acta ---
        lugar = request.form.get('unidad') 
        numero_acta = request.form.get('numero_acta') 
        fecha = request.form.get('fecha_reunion')
        h_inicio = request.form.get('hora_inicio')
        titulo = request.form.get('titulo')
        puntos = request.form.get('puntos_tratados')
        obs = request.form.get('observaciones')
        antecedentes = request.form.get('antecedentes') # Mapeado a objetivo

        try:
            # 1. Guardar Acta
            nuevo_registro = {
                "anfitrion_id": session['user_id'],
                "titulo": titulo,
                "objetivo": antecedentes,
                "lugar": lugar,
                "numero_acta": numero_acta,
                "fecha_reunion": f"{fecha}T{h_inicio}:00",
                "puntos_tratados": puntos,
                "conclusiones": obs,
                "estado": "Abierta"
            }
            response = supabase.table("actas").insert(nuevo_registro).execute()
            acta_id = response.data[0]['id']

            # --- B. Guardar Compromisos Adquiridos ---
            tareas = request.form.getlist('descripcion_tarea[]')
            responsables = request.form.getlist('responsable_nombre[]')
            fechas_e = request.form.getlist('fecha_entrega[]')

            lista_compromisos = []
            for i in range(len(tareas)):
                if tareas[i].strip():
                    lista_compromisos.append({
                        "acta_id": acta_id,
                        "descripcion_tarea": tareas[i],
                        "responsable_nombre": responsables[i],
                        "fecha_entrega": fechas_e[i] if fechas_e[i] else None,
                        "estado_tarea": "Pendiente"
                    })

            if lista_compromisos:
                supabase.table("compromisos").insert(lista_compromisos).execute()

            flash("Acta y compromisos registrados con éxito.")
            return redirect(url_for('ver_acta', acta_id=acta_id))

        except Exception as e:
            print(f"Error: {e}")
            flash("Hubo un error al registrar los datos.")
            return redirect(url_for('nueva_acta'))

    return render_template('nueva_acta.html', nombre=session['nombre'])

@app.route('/acta/<acta_id>')
@login_required # Usamos el decorador de seguridad que creamos antes
def ver_acta(acta_id):
    try:
        # 1. Traer los datos del acta (incluye el access_token para el QR)
        acta_res = supabase.table("actas").select("*").eq("id", acta_id).single().execute()
        
        # 2. Traer los participantes que ya han firmado
        part_res = supabase.table("participantes_acta").select("*").eq("acta_id", acta_id).execute()
        
        # 3. Traer los compromisos registrados
        comp_res = supabase.table("compromisos").select("*").eq("acta_id", acta_id).execute()
        
        # 4. Renderizar la vista con todos los datos necesarios
        return render_template('detalle_acta.html', 
                               acta=acta_res.data, 
                               participantes=part_res.data,
                               compromisos=comp_res.data,
                               nombre=session.get('nombre')) # Usamos .get por seguridad

    except Exception as e:
        print(f"Error al cargar detalle de acta: {e}")
        flash("No se pudo cargar la información del acta.")
        return redirect(url_for('dashboard'))

@app.route('/agregar_participante', methods=['POST'])
def agregar_participante():
    if 'user_id' not in session: return redirect(url_for('index'))
    acta_id = request.form.get('acta_id')
    try:
        nuevo_p = {
            "acta_id": acta_id,
            "cedula": request.form.get('cedula'),
            "nombres_completos": request.form.get('nombres_completos'),
            "unidad": request.form.get('unidad'),
            "correo": request.form.get('correo')
        }
        supabase.table("participantes_acta").insert(nuevo_p).execute()
        flash("Participante agregado.")
    except Exception as e:
        flash("Error.")
    return redirect(url_for('ver_acta', acta_id=acta_id))
    
@app.route('/actualizar_estado_acta/<acta_id>', methods=['POST'])
@login_required
def actualizar_estado_acta(acta_id):
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        # 1. Actualizar el acta
        supabase.table("actas").update({"estado": nuevo_estado}).eq("id", acta_id).execute()
        
        # 2. REGISTRO DE AUDITORÍA
        log_data = {
            "usuario_id": session.get('user_id'),
            "accion": f"CAMBIO DE ESTADO: {nuevo_estado.upper()}",
            "detalles": {
                "id_acta": acta_id,
                "nuevo_estado": nuevo_estado,
                "mensaje": f"El usuario cambió el estado del acta a {nuevo_estado}"
            },
            "ip_address": get_client_ip()
        }
        supabase.table("auditoria_sistema").insert(log_data).execute()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/imprimir_acta/<acta_id>')
@login_required
def imprimir_acta(acta_id):
    try:
        # 1. Obtener todos los datos de Supabase
        acta = supabase.table("actas").select("*").eq("id", acta_id).single().execute()
        participantes = supabase.table("participantes_acta").select("*").eq("acta_id", acta_id).execute()
        compromisos = supabase.table("compromisos").select("*").eq("acta_id", acta_id).execute()

        # 2. Renderizar el HTML
        html_content = render_template(
            'acta_pdf.html',
            acta=acta.data,
            participantes=participantes.data,
            compromisos=compromisos.data
        )

        # 3. Convertir HTML a PDF en memoria
        pdf_out = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_out)

        # 4. Verificar si hubo errores
        if pisa_status.err:
            return "Error al generar el PDF", 500

        # =========================================================
        # --- INICIO DE LA NUEVA LÓGICA DE ENVÍO DE CORREOS ---
        # =========================================================
        try:
            # A. Guardar el PDF temporalmente en el servidor
            ruta_temporal = f"Acta_Temporal_{acta_id}.pdf"
            with open(ruta_temporal, "wb") as f:
                f.write(pdf_out.getvalue())

            # B. Extraer todos los correos de la variable 'participantes' que ya buscamos arriba
            # Esto crea una lista limpia: ['juan@gmail.com', 'pedro@policia.gob.ec']
            correos_destinos = [p['correo'] for p in participantes.data if p.get('correo')]
            numero_acta = acta.data.get('numero_acta', f"Acta_{acta_id}")

            # C. Si encontramos correos, llamamos a tu función para enviar el PDF
            if correos_destinos:
                print(f"Enviando PDF a: {correos_destinos}")
                enviar_pdf_acta(correos_destinos, numero_acta, ruta_temporal)
            else:
                print("No hay correos registrados en esta acta para enviar el PDF.")

            # D. Eliminar el archivo temporal para no ocupar espacio
            if os.path.exists(ruta_temporal):
                os.remove(ruta_temporal)

        except Exception as error_correo:
            print(f"Error en el proceso de envío de correos: {error_correo}")
        # =========================================================
        # --- FIN DE LA NUEVA LÓGICA ---
        # =========================================================

        # 5. Preparar la respuesta para el navegador (descarga el PDF en tu pantalla)
        response = make_response(pdf_out.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        # Usamos el número de acta real para el nombre del archivo descargado
        nombre_archivo = acta.data.get('numero_acta', f'Acta_{acta_id}')
        response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}.pdf'
        
        return response

    except Exception as e:
        print(f"Error generando PDF: {e}")
        return "Error interno del servidor", 500

@app.route('/registro_asistente/<acta_id>')
def formulario_asistente(acta_id):
    # Esta ruta es pública, los asistentes la abren al escanear el QR
    try:
        acta = supabase.table("actas").select("titulo").eq("id", acta_id).single().execute()
        return render_template('registro_publico.html', acta_id=acta_id, titulo=acta.data['titulo'])
    except:
        return "El acta no existe o ha sido cerrada.", 404

@app.route('/guardar_firma_asistente', methods=['POST'])
def guardar_firma_asistente():
    # --- Configuración de Estilos USECIPOL ---
    # Colores Azules Institucionales
    color_principal = "#1a3275" # Azul oscuro
    color_borde = "#3498db"      # Azul claro/acento

    # Icono SVG de Sirena Policial (Elegante y minimalista en blanco)
    icono_sirena_blanca = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white" style="width:65px; height:65px;">
        <path d="M12 2a1 1 0 0 1 1 1v2a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1zM18.364 4.222a1 1 0 0 1 1.414 1.414l-1.414 1.414a1 1 0 0 1-1.414-1.414l1.414-1.414zM5.636 4.222l1.414 1.414a1 1 0 1 1-1.414 1.414L4.222 5.636a1 1 0 0 1 1.414-1.414zM21 13a1 1 0 1 1 0 2h-2a1 1 0 1 1 0-2h2zM5 13H3a1 1 0 1 1 0-2h2a1 1 0 1 1 0 2z"/>
        <path d="M17 14.5V13a5 5 0 0 0-10 0v1.5a3.5 3.5 0 0 0-2 3.148V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1.352a3.5 3.5 0 0 0-2-3.148zM9 13a3 3 0 1 1 6 0v1H9v-1z"/>
        <path d="M6 21h12a1 1 0 0 1 0 2H6a1 1 0 0 1 0-2z"/>
    </svg>
    """

    # Template HTML base para tarjetas
    def generar_tarjeta_azul(titulo, mensaje, icono=None, mostrar_boton=False, error_critico=None):
        icono_html = f"<div style='margin-bottom: 20px; padding: 15px; display:inline-block; border-radius: 50%; background-color:{color_principal};'>{icono}</div>" if icono else ""
        boton_html = f"<a href='javascript:history.back()' style='display: inline-block; margin-top: 25px; padding: 12px 24px; background-color: {color_principal}; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 10px rgba(26,50,117,0.3);'>Volver al formulario</a>" if mostrar_boton else ""
        error_html = f"<p style='color: #888; font-size: 11px; margin-top: 25px; border-top: 1px solid #ddd; padding-top: 15px; word-wrap: break-word; text-align:left;'>Detalle técnico: {error_critico}</p>" if error_critico else ""
        
        return f"""
        <div style='display:flex; justify-content:center; align-items:center; min-height:80vh; background-color: #f6f8fa; font-family: sans-serif; padding: 20px;'>
            <div style='max-width: 450px; width: 100%; padding: 40px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; border-top: 8px solid {color_borde}; background-color: #fff;'>
                {icono_html}
                <h2 style='color: {color_principal}; margin-top:10px; font-size: 26px; font-weight: 800;'>{titulo}</h2>
                <p style='color: #555; font-size: 16px; line-height: 1.6; margin-top: 15px;'>{mensaje}</p>
                {boton_html}
                {error_html}
            </div>
        </div>
        """

    # --- INICIO DE LÓGICA DE GUARDADO ---
    try:
        # 1. Recolectamos los datos
        acta_id = request.form.get('acta_id', '')
        cedula = request.form.get('cedula', '')
        nombres = request.form.get('nombres_completos', '')
        unidad = request.form.get('unidad', '')      
        correo = request.form.get('correo', '')
        firma_base64 = request.form.get('firma_base64', '')
        
        # 2. Validación: Términos
        if request.form.get('terminos') != 'on':
            return generar_tarjeta_azul(
                "Validación de Datos",
                "Debe aceptar el uso de sus datos personales para registrar la asistencia.",
                icono=icono_sirena_blanca, 
                mostrar_boton=True
            ), 400

        # 3. Validación: Firma
        if not firma_base64 or len(firma_base64) < 1000:
             return generar_tarjeta_azul(
                "Firma Requerida",
                "Por favor, registre su firma digital en el recuadro antes de enviar.",
                icono=icono_sirena_blanca,
                mostrar_boton=True
            ), 400
            
        # 4. Armamos los datos
        datos_a_guardar = {
            "acta_id": acta_id,
            "cedula": cedula,
            "nombres_completos": nombres,
            "unidad": unidad, 
            "correo": correo,
            "trazo_firma_url": firma_base64,
            "es_firma_electronica": False
        }

        # 5. Guardamos en Supabase
        supabase.table("participantes_acta").insert(datos_a_guardar).execute()

        # 6. ÉXITO (Ahora usa la sirena en el círculo azul)
        return generar_tarjeta_azul(
            "Registro Exitoso", 
            "Su asistencia y firma han sido registradas correctamente en el sistema de USECIPOL.",
            icono=icono_sirena_blanca
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # 7. REGISTRO DUPLICADO
        if "already exists" in error_msg or "23505" in error_msg or "duplicate key" in error_msg.lower():
            return generar_tarjeta_azul(
                "Registro Existente", 
                "Usted ya ha registrado su firma para esta acta anteriormente. No es necesario volver a hacerlo.",
                icono=icono_sirena_blanca
            ), 200
            
        # 8. ERROR REAL
        print(f"Error técnico crítico: {error_msg}")
        return generar_tarjeta_azul(
            "Error de Sistema", 
            "No se pudo completar la operación. Por favor contacte a soporte técnico.",
            icono=icono_sirena_blanca, 
            error_critico=error_msg 
        ), 500
        
@app.route('/editar_acta/<acta_id>')
@login_required
def editar_acta(acta_id):
    try:
        # 1. Obtener los datos actuales
        acta_res = supabase.table("actas").select("*").eq("id", acta_id).single().execute()
        
        # Bloqueo de seguridad: No editar si ya está cerrada
        if acta_res.data['estado'] == 'Cerrada':
            flash("No se puede editar un acta que ya ha sido cerrada.")
            return redirect(url_for('ver_acta', acta_id=acta_id))
            
        return render_template('editar_acta.html', acta=acta_res.data)
    except Exception as e:
        print(f"Error al cargar edición: {e}")
        return redirect(url_for('dashboard'))
        
# En app.py, añade esta nueva ruta:

# En app.py
@app.route('/api/buscar_perfil/<cedula>')
def buscar_perfil(cedula):
    try:
        # Consulta exacta basada en tu diagrama de base de datos
        res = supabase.table("perfiles").select(
            "nombres, apellidos, correo_institucional, unidad_administrativa, grado_policial, cargo"
        ).eq("cedula", cedula).execute()

        if res.data and len(res.data) > 0:
            p = res.data[0]
            return jsonify({
                "success": True,
                "nombre_completo": f"{p['nombres']} {p['apellidos']}",
                "correo": p['correo_institucional'],
                "grado_cargo": f"{p['grado_policial']} - {p['cargo']}",
                "unidad": p['unidad_administrativa']
            })
        return jsonify({"success": False, "mensaje": "No encontrado"})
    except Exception as e:
        # Esto imprimirá el error real en tu terminal negra de VS Code
        print(f"Error en Supabase: {str(e)}") 
        return jsonify({"success": False, "error": str(e)}), 500
@app.route('/cerrar_acta/<acta_id>', methods=['POST'])
@login_required
def cerrar_acta(acta_id):
    # 1. Cambiamos el estado en la base de datos
    supabase.table("actas").update({"estado": "Cerrada"}).eq("id", acta_id).execute()
    
    # 2. DISPARAMOS EL ENVÍO DE CORREOS
    enviar_acta_participantes(acta_id)
    
    flash("Acta cerrada y enviada a todos los participantes.")
    return redirect(url_for('ver_acta', acta_id=acta_id))

def enviar_actas_por_correo(lista_correos, acta_id):
    # Aquí configuras tu servidor de correo institucional
    # Se recorre la lista_correos y se envía el PDF adjunto (o el link de descarga)
    pass

def enviar_acta_participantes(acta_id, pdf_path=None):
    try:
        # 1. Obtener correos de los firmantes
        participantes = supabase.table("firmas_actas").select("correo").eq("acta_id", acta_id).execute()
        
        # Configuración del servidor (Ejemplo con Gmail)
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = "tu_correo@gmail.com"
        sender_password = "tu_password_de_aplicacion"

        for p in participantes.data:
            destinatario = p['correo']
            
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = destinatario
            msg['Subject'] = f"Acta de Reunión Finalizada - ID: {acta_id}"

            cuerpo = "Estimado participante, se adjunta el acta de reunión debidamente finalizada y firmada."
            msg.attach(MIMEText(cuerpo, 'plain'))

            # Lógica para enviar el correo
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
                
            print(f"Correo enviado a {destinatario}")
    except Exception as e:
        print(f"Error enviando correos: {e}")


# --- NUEVO ENDPOINT PARA BUSCAR PERFILES POR CÉDULA ---
# En app.py, agrega esta nueva ruta:

@app.route('/api/obtener_perfil/<cedula>')
def obtener_perfil(cedula):
    try:
        # Buscamos en tu tabla 'perfiles'
        perfil_res = supabase.table("perfiles").select("*").eq("cedula", cedula).execute()
        
        if perfil_res.data:
            p = perfil_res.data[0]
            
            # Unimos los nombres y apellidos para el formulario
            nombres = p.get('nombres') or ''
            apellidos = p.get('apellidos') or ''
            nombre_completo = f"{nombres} {apellidos}".strip()
            
            # Mapeamos con los nombres EXACTOS de tus columnas en Supabase
            return jsonify({
                "existe": True,
                "perfil": {
                    "nombres_completos": nombre_completo,
                    "grado_cargo": p.get('grado_policial', ''), 
                    "unidad": p.get('unidad_administrativa', ''),
                    "correo": p.get('correo_institucional', '')
                }
            })
        else:
            return jsonify({"existe": False})
            
    except Exception as e:
        print(f"Error en Supabase al buscar cédula: {e}")
        return jsonify({"existe": False, "error": str(e)}), 500


def enviar_pdf_acta(lista_correos, numero_acta, ruta_pdf):
    # ⚠️ TUS CREDENCIALES
    remitente = "soporteactas@usecipol.edu.ec" 
    password = "zohgksmdysfhfrey" 

    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    
    # Si recibimos una lista de correos (ej: ['a@a.com', 'b@b.com']), los unimos con comas
    if isinstance(lista_correos, list):
        mensaje['To'] = ", ".join(lista_correos)
    else:
        mensaje['To'] = lista_correos
        
    mensaje['Subject'] = f"Acta Aprobada y Firmada: {numero_acta} - USECIPOL"

    # 1. Cuerpo del correo
    cuerpo_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="border-bottom: 2px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px;">
                <h2 style="color: #1e3a8a;">Sistema de Actas de Reunión - USECIPOL</h2>
            </div>
            <p>Saludos cordiales,</p>
            <p>Se adjunta a este correo el documento final correspondiente al acta <strong>{numero_acta}</strong>, la cual ya cuenta con las firmas de los participantes requeridos.</p>
            <p>Por favor, revise el documento adjunto para su conocimiento y fines pertinentes respecto a los compromisos adquiridos.</p>
            <br>
            <p style="font-size: 12px; color: #666;">Este es un mensaje automático del sistema, por favor no responda a este correo.</p>
        </body>
    </html>
    """
    mensaje.attach(MIMEText(cuerpo_html, 'html'))

    # 2. Leer y adjuntar el PDF
    try:
        # Abrimos el PDF en modo lectura binaria ("rb")
        with open(ruta_pdf, "rb") as archivo_pdf:
            # Creamos el adjunto
            adjunto = MIMEApplication(archivo_pdf.read(), _subtype="pdf")
            # Le damos el nombre con el que aparecerá en el correo (ej. ACTA_TH_001.pdf)
            nombre_archivo_adjunto = f"{numero_acta}.pdf"
            adjunto.add_header('Content-Disposition', 'attachment', filename=nombre_archivo_adjunto)
            # Lo pegamos al mensaje
            mensaje.attach(adjunto)
    except FileNotFoundError:
        print(f"❌ ERROR: No se encontró el archivo PDF en la ruta: {ruta_pdf}")
        return False
    except Exception as e:
        print(f"❌ ERROR al leer el PDF: {e}")
        return False

    # 3. Enviar el correo
    try:
        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.login(remitente, password)
        servidor.send_message(mensaje)
        servidor.quit()
        print(f"✅ Correo con PDF enviado exitosamente a: {mensaje['To']}")
        return True
    except Exception as e:
        print(f"❌ ERROR de conexión al enviar correo: {e}")
        return False

        
@app.route('/guardar_firma_publica', methods=['POST'])
def guardar_firma_publica():
    datos = request.form
    cedula = datos.get('cedula')
    
    try:
        # 1. Intentar registrar/actualizar el perfil primero
        perfil_data = {
            "cedula": cedula,
            "nombres": datos.get('nombres_completos'), # Deberías separar si tu tabla pide nombres/apellidos
            "cargo": datos.get('unidad_cargo'),
            "email": datos.get('correo'),
            "unidad": datos.get('unidad')
        }
        
        # .upsert() buscará por la "cedula" (debe ser tu Primary Key o tener un Unique index)
        # Si existe, lo actualiza. Si no, lo crea.
        supabase.table("perfiles").upsert(perfil_data, on_conflict="cedula").execute()

        # 2. Guardar la firma en el acta (tu lógica actual)
        # ... aqui va tu codigo de inserción en firmas_actas ...

        return render_template('exito_firma.html')
    except Exception as e:
        return f"Error: {e}"

@app.route('/api/generar_secuencial', methods=['GET'])
def generar_secuencial():
    # 1. Recibimos qué departamento eligió el usuario (Ej: 'TH')
    unidad_siglas = request.args.get('unidad')
    
    if not unidad_siglas:
        return jsonify({"error": "Faltan siglas"}), 400

    # 2. Obtenemos el año actual
    año_actual = datetime.now().year

    try:
        # 3. Buscamos en Supabase todas las actas de esta unidad y este año
        # NOTA: Asegúrate de que tu tabla se llame 'actas' y tenga la columna 'numero_acta'
        patron_busqueda = f'ACTA_{unidad_siglas}_%_{año_actual}'
        respuesta = supabase.table('actas').select('numero_acta').like('numero_acta', patron_busqueda).execute()
        
        datos = respuesta.data
        
        # 4. Calculamos el siguiente número
        if not datos:
            # Si no hay ninguna, empezamos en 1
            siguiente_numero = 1
        else:
            numeros = []
            for fila in datos:
                try:
                    # Cortamos el texto: "ACTA_TH_001_2026" -> sacamos el "001" y lo volvemos número
                    partes = fila['numero_acta'].split('_')
                    if len(partes) >= 3:
                        numeros.append(int(partes[2]))
                except ValueError:
                    pass
            
            # Buscamos el número más alto y le sumamos 1
            siguiente_numero = max(numeros) + 1 if numeros else 1

        # 5. Armamos el formato final (Ej. 1 -> 001)
        numero_formateado = f"{siguiente_numero:03d}"
        acta_final = f"ACTA_{unidad_siglas}_{numero_formateado}_{año_actual}"
        
        return jsonify({"numero_acta": acta_final})

    except Exception as e:
        print(f"Error generando secuencial: {e}")
        return jsonify({"error": "Error interno"}), 500


@app.route('/registro_publico/<token>')
def registro_publico_token(token):
    try:
        # Buscamos el acta que coincida con el token y esté abierta
        response = supabase.table("actas")\
            .select("id, titulo, estado")\
            .eq("access_token", token)\
            .eq("estado", "Abierta")\
            .execute()

        # Si no hay datos en la lista 'data', el token no existe o el acta se cerró
        if not response.data or len(response.data) == 0:
            return render_template('error_firma.html', 
                                   mensaje="Enlace No Válido", 
                                   subtitulo="El acta no existe o ya fue cerrada por el administrador.")

        # Si existe, tomamos el primer registro de la lista
        acta_encontrada = response.data[0]
        
        return render_template('registro_publico.html', 
                               acta_id=acta_encontrada['id'], 
                               titulo=acta_encontrada['titulo'])
                               
    except Exception as e:
        print(f"Error de validación: {e}")
        return render_template('error_firma.html', 
                               mensaje="Error de Conexión", 
                               subtitulo="No pudimos verificar el acta. Intente nuevamente.")
if __name__ == '__main__':
    app.run(debug=True)