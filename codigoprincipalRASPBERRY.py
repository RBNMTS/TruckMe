from flask import Flask, render_template
from flask import send_from_directory
from flask import Flask, Response, request
import cv2
import smbus
import time
import threading

app = Flask(__name__, template_folder='template')
#app = Flask(__name__)

# Configurações do MD25
MD25_ADDRESS = 0x58
SPEED1 = 0x00  # Motor 1
SPEED2 = 0x01  # Motor 2
MODE = 0x0F    # Modo de operação

# Configurações do LIDAR
LIDAR_ADDRESS = 0x62
MEASURE_REG = 0x00
HIGH_BYTE = 0x0F
LOW_BYTE = 0x10

# Velocidades dos motores
VEL_FRENTE = 140
VEL_TRAS = 90
VEL_PARAR = 128
VEL_ESQUERDA = 130
VEL_DIREITA = 160

# Distância mínima de segurança (cm)
DISTANCIA_MINIMA = 50

# Inicializar barramento I2C
bus = smbus.SMBus(1)
bus.write_byte_data(MD25_ADDRESS, MODE, 0)  # Configurar modo do MD25

# Variável global para controlo de emergência
emergencia = False
ultima_distancia = 0

# Inicializar câmera
cap = cv2.VideoCapture(0)
cap.set(3, 640)  # Largura
cap.set(4, 480)  # Altura

def set_motors(speed1, speed2):
    """Controla os motores com valores entre 0-255"""
    global emergencia
    
    # Se estiver em estado de emergência, força a paragem dos motores
    if emergencia:
        bus.write_byte_data(MD25_ADDRESS, SPEED1, VEL_PARAR)
        bus.write_byte_data(MD25_ADDRESS, SPEED2, VEL_PARAR)
    else:
        bus.write_byte_data(MD25_ADDRESS, SPEED1, speed1)
        bus.write_byte_data(MD25_ADDRESS, SPEED2, speed2)

def medir_distancia():
    """Mede a distância usando o LIDAR"""
    try:
        bus.write_byte_data(LIDAR_ADDRESS, MEASURE_REG, 0x04)  # Iniciar medição
        time.sleep(0.02)  # Esperar resposta
        high_byte = bus.read_byte_data(LIDAR_ADDRESS, HIGH_BYTE)
        low_byte = bus.read_byte_data(LIDAR_ADDRESS, LOW_BYTE)
        distancia = (high_byte << 8) + low_byte
        return distancia
    except Exception as e:
        print(f"Erro ao medir distância: {e}")
        return -1  # Retorna -1 em caso de erro

def monitorar_obstaculos():
    """Thread que monitora continuamente a distância e para os motores se necessário"""
    global emergencia, ultima_distancia
    
    while True:
        distancia = medir_distancia()
        ultima_distancia = distancia
        
        # Ativa emergência se o objeto estiver muito próximo
        if 0 < distancia < DISTANCIA_MINIMA:
            if not emergencia:
                print(f"EMERGÊNCIA! Obstáculo detectado a {distancia} cm")
            emergencia = True
            set_motors(VEL_PARAR, VEL_PARAR)
        else:
            emergencia = False
            
        time.sleep(0.1)  # Verifica a cada 100ms

def generate_frames():
    """Gera frames da câmera para streaming"""
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Falha ao capturar frame")
            break
        
        # Adiciona informação da distância no frame
        cv2.putText(frame, f"Distancia: {ultima_distancia} cm", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if emergencia:
            cv2.putText(frame, "OBSTACULO DETECTADO!", (10, 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """Rota para streaming de vídeo"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/controle')
def controle():
    """Rota para receber comandos de controlo"""
    global emergencia
    
    comando = request.args.get('comando')
    print(f"Comando recebido: {comando}")
    
    # Se estiver em emergência, ignora todos os comandos exceto "parar"
    if emergencia and comando != "parar":
        return "EMERGENCIA: Obstáculo detectado!", 403
    
    if comando == 'frente':
        set_motors(VEL_FRENTE, VEL_FRENTE)
    elif comando == 'esquerda':
        set_motors(VEL_ESQUERDA, VEL_FRENTE)
    elif comando == 'direita':
        set_motors(VEL_FRENTE, VEL_ESQUERDA)
    elif comando == 'parar':
        set_motors(VEL_PARAR, VEL_PARAR)
    elif comando == 'tras':
        set_motors(VEL_TRAS, VEL_TRAS)
    else:
        return "Comando inválido", 400
    
    return "OK"

@app.route('/status')
def status():
    """Rota para verificar o status do robô"""
    return {
        "emergencia": emergencia,
        "distancia": ultima_distancia,
        "motores": "parado" if emergencia else "ativo"
    }

@app.route('/')
def index():
    """Página inicial com visualização da câmera"""
    return render_template('index.html')

@app.route('/autorais')
def autorais():
    """Página com visualização da D.autorias"""
    return render_template('autorais.html')

@app.route('/diogo')
def diogo():
    """Rota de imagem"""
    return send_from_directory('/home/rufidiogo/testes/template/img', 'diogo.png')

@app.route('/ruben')
def ruben():
    """Rota de imagem"""
    return send_from_directory('/home/rufidiogo/testes/template/img', 'ruben.png')

def cleanup():
    """Limpeza ao encerrar o programa"""
    set_motors(VEL_PARAR, VEL_PARAR)
    cap.release()
    print("Recursos libertados")

if __name__ == "__main__":
    try:
        # Verificar conexão com a câmera
        if not cap.isOpened():
            raise RuntimeError("Não foi possível abrir a câmera")
        
        # Iniciar thread de monitoramento de obstáculos
        threading.Thread(target=monitorar_obstaculos, daemon=True).start()
        
        # Iniciar servidor Flask
        print("Iniciando servidor...")
        app.run(host='0.0.0.0', port=5000, threaded=True)
    except KeyboardInterrupt:
        print("Encerrando pelo utilizador...")
    finally:
        cleanup()