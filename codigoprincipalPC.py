import time
import cv2
import requests
import numpy as np
import mediapipe as mp

# Configurações
URL_VIDEO = 'http://192.168.1.250:5000/video_feed'
URL_COMANDO = 'http://192.168.1.250:5000/controle'
URL_STATUS = 'http://192.168.1.250:5000/status'

# Inicializar o MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)
mp_draw = mp.solutions.drawing_utils

# Cores para a interface
COR_NORMAL = (0, 255, 0)
COR_ALERTA = (0, 255, 255)
COR_EMERGENCIA = (0, 0, 255)

def conectar_video():
    """Estabelece conexão com o stream de vídeo"""
    cap = cv2.VideoCapture(URL_VIDEO)
    if not cap.isOpened():
        print("Erro ao conectar ao vídeo. Verifique se o servidor está ativo.")
        return None
    return cap

def enviar_comando(comando):
    """Envia comando para o robô"""
    try:
        response = requests.get(URL_COMANDO, params={'comando': comando}, timeout=2)
        if response.status_code == 200:
            print(f"Comando '{comando}' enviado com sucesso!")
            return True
        elif response.status_code == 403:
            print("Robô em estado de emergência! Comando ignorado.")
            return False
        else:
            print(f"Erro ao enviar comando: {response.status_code}")
            return False
    except Exception as e:
        print(f"Falha na comunicação: {e}")
        return False

def verificar_status():
    """Obtém o status atual do robô"""
    try:
        response = requests.get(URL_STATUS, timeout=1)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return {"emergencia": False, "distancia": -1}

def contar_dedos(frame):
    """Detecta e conta dedos levantados"""
    altura, largura, _ = frame.shape
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # Detecção de dedos esticados
            dedos_esticados = 0
            
            # Polegar (eixo X)
            if hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP].x < \
               hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_IP].x:
                dedos_esticados += 1
            
            # Outros dedos (eixo Y)
            for tip, dip in [
                (mp_hands.HandLandmark.INDEX_FINGER_TIP, mp_hands.HandLandmark.INDEX_FINGER_DIP),
                (mp_hands.HandLandmark.MIDDLE_FINGER_TIP, mp_hands.HandLandmark.MIDDLE_FINGER_DIP),
                (mp_hands.HandLandmark.RING_FINGER_TIP, mp_hands.HandLandmark.RING_FINGER_DIP),
                (mp_hands.HandLandmark.PINKY_TIP, mp_hands.HandLandmark.PINKY_DIP)
            ]:
                if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[dip].y:
                    dedos_esticados += 1

            # Posição da mão na tela
            posicao_x = int(hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP].x * largura)
            return dedos_esticados, posicao_x
    
    return 0, None

def determinar_comando(dedos, posicao_x, largura):
    """Determina o comando com base nos gestos"""
    if dedos == 0:
        return None
    
    limite_esquerda = largura // 3
    limite_direita = 2 * (largura // 3)
    
    if dedos == 1:
        if posicao_x < limite_esquerda:
            return "esquerda"
        elif posicao_x > limite_direita:
            return "direita"
        else:
            return "frente"
    elif dedos == 5:
        return "tras"
    elif dedos == 3:
        return "parar"
    
    return None

def exibir_informacoes(frame, dedos, posicao_x, status):
    """Exibe informações na tela"""
    # Informações de detecção
    cv2.putText(frame, f"Dedos: {dedos}", (10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, COR_NORMAL, 2)
    
    if posicao_x is not None:
        cv2.putText(frame, f"Posicao X: {posicao_x}", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, COR_NORMAL, 2)
    
    # Status do robô
    cor_status = COR_EMERGENCIA if status['emergencia'] else COR_NORMAL
    texto_status = f"Distancia: {status['distancia']} cm"
    if status['emergencia']:
        texto_status += " (OBSTACULO!)"
    
    cv2.putText(frame, texto_status, (10, 110), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor_status, 2)

def controle_principal():
    """Função principal de controlo"""
    cap = conectar_video()
    if cap is None:
        return
    
    ultimo_comando = None
    tempo_ultimo_comando = time.time()
    ultimo_status = {'emergencia': False, 'distancia': -1}
    
    while True:
        # Obter frame do vídeo
        ret, frame = cap.read()
        if not ret:
            print("Conexão perdida. Tentando reconectar...")
            cap.release()
            time.sleep(2)
            cap = conectar_video()
            if cap is None:
                break
            continue
        
        # Obter status do robô
        if time.time() - tempo_ultimo_comando > 0.5:  # Verificar status a cada 0.5s
            ultimo_status = verificar_status()
        
        # Detectar gestos
        dedos, posicao_x = contar_dedos(frame)
        largura = frame.shape[1]
        
        # Determinar comando
        comando = determinar_comando(dedos, posicao_x, largura)
        
        # Enviar comando se necessário
        if comando and (comando != ultimo_comando or time.time() - tempo_ultimo_comando > 1):
            if enviar_comando(comando):
                ultimo_comando = comando
                tempo_ultimo_comando = time.time()
        
        # Exibir informações
        exibir_informacoes(frame, dedos, posicao_x, ultimo_status)
        
        # Mostrar frame
        cv2.imshow("Controlo por Gestos - Pressione Q para sair", frame)
        
        # Verificar tecla de saída
        if cv2.waitKey(1) & 0xFF == ord('q'):
            enviar_comando("parar")
            break
    
    # Liberar recursos
    cap.release()
    cv2.destroyAllWindows()
    print("Programa encerrado.")

if __name__ == "__main__":
    controle_principal()