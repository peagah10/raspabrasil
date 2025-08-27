import os
import random
import string
from datetime import datetime, date
from flask import Flask, request, jsonify, session
from dotenv import load_dotenv

# Inicializar Supabase com configuração compatível
try:
    from supabase import create_client, Client
    supabase_available = True
except ImportError:
    supabase_available = False
    print("⚠️ Supabase não disponível")

import mercadopago
import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv(
    'SECRET_KEY', 'raspa-brasil-super-secret-key-2024-seguro'
)

# Configurações do Supabase
SUPABASE_URL = os.getenv(
    'SUPABASE_URL', "https://ngishqxtnkgvognszyep.supabase.co"
)
SUPABASE_KEY = os.getenv(
    'SUPABASE_KEY',
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5naXNocXh0bmtndm9nbnN6eWVwIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NTI1OTMwNjcsImV4cCI6MjA2ODE2OTA2N30."
    "FOksPjvS2NyO6dcZ_j0Grj3Prn9OP_udSGQwswtFBXE"
)

# Configurações do Mercado Pago
MP_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
sdk = None

# 🚫 CONFIGURAÇÕES CRÍTICAS DO SISTEMA - INTEGRAÇÃO COM INDEX.HTML
TOTAL_RASPADINHAS = 10000
PREMIOS_TOTAIS = 2000
LIMITE_PREMIOS = 1000  # ⚠️ CRÍTICO: SÓ LIBERA PRÊMIOS APÓS 1000 VENDAS OBRIGATÓRIAS
WHATSAPP_NUMERO = "5582996092684"
PERCENTUAL_COMISSAO_AFILIADO = 50  # 50% de comissão

# Inicializar cliente Supabase
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Testar conexão
        test_response = supabase.table('rb_configuracoes').select(
            'rb_chave'
        ).limit(1).execute()
        print("✅ Supabase conectado e testado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao conectar com Supabase: {str(e)}")
        supabase = None

# Configurar Mercado Pago
try:
    if MP_ACCESS_TOKEN:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        print("✅ Mercado Pago SDK configurado com sucesso")
    else:
        print("❌ Token do Mercado Pago não encontrado")
        print("⚠️ Sistema funcionará apenas com pagamentos simulados")
except Exception as e:
    print(f"❌ Erro ao configurar Mercado Pago: {str(e)}")
    print("⚠️ Sistema funcionará apenas com pagamentos simulados")


def log_sistema_bloqueio(vendas_atuais, limite, acao, resultado):
    """Log detalhado do sistema de bloqueio de prêmios"""
    status = "🚫 BLOQUEADO" if vendas_atuais < limite else "✅ LIBERADO"
    print(f"{status} | Vendas: {vendas_atuais}/{limite} | Ação: {acao} | Resultado: {resultado}")


def verificar_sistema_liberado():
    """Verifica se o sistema de prêmios está liberado"""
    vendas = obter_total_vendas()
    liberado = vendas >= LIMITE_PREMIOS
    
    if liberado:
        print(f"🎁 SISTEMA LIBERADO: {vendas}/{LIMITE_PREMIOS} vendas - Prêmios ATIVOS")
    else:
        print(f"🚫 SISTEMA BLOQUEADO: {vendas}/{LIMITE_PREMIOS} vendas - Prêmios TRAVADOS")
        print(f"⏳ Faltam {LIMITE_PREMIOS - vendas} vendas para liberar prêmios")
    
    return liberado


def log_payment_change(payment_id, status_anterior, status_novo,
                       webhook_data=None):
    """Registra mudanças de status de pagamento"""
    if not supabase:
        return False
    try:
        supabase.table('rb_logs_pagamento').insert({
            'rb_payment_id': payment_id,
            'rb_status_anterior': status_anterior,
            'rb_status_novo': status_novo,
            'rb_webhook_data': webhook_data
        }).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao registrar log: {str(e)}")
        return False


def gerar_codigo_antifraude():
    """Gera código único no formato RB-XXXXX-YYY"""
    numero = random.randint(10000, 99999)
    letras = ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=3
    ))
    return f"RB-{numero}-{letras}"


def gerar_codigo_roda():
    """Gera código único para Roda Brasil no formato RR-XXXXX-YYY"""
    numero = random.randint(10000, 99999)
    letras = ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=3
    ))
    return f"RR-{numero}-{letras}"


def gerar_codigo_afiliado():
    """Gera código único para afiliado no formato AF-XXXXX"""
    numero = random.randint(100000, 999999)
    return f"AF{numero}"


def verificar_codigo_unico(codigo, tabela='rb_ganhadores', campo='rb_codigo'):
    """Verifica se o código é único no banco de dados"""
    if not supabase:
        return True
    try:
        response = supabase.table(tabela).select(campo).eq(
            campo, codigo
        ).execute()
        return len(response.data) == 0
    except Exception:
        return True


def gerar_codigo_unico():
    """Gera um código antifraude único"""
    max_tentativas = 10
    for _ in range(max_tentativas):
        codigo = gerar_codigo_antifraude()
        if verificar_codigo_unico(codigo):
            return codigo
    return f"RB-{random.randint(10000, 99999)}-{uuid.uuid4().hex[:3].upper()}"


def gerar_codigo_unico_roda():
    """Gera um código único para Roda Brasil"""
    max_tentativas = 10
    for _ in range(max_tentativas):
        codigo = gerar_codigo_roda()
        if verificar_codigo_unico(codigo, 'rb_ganhadores_roda', 'rb_codigo'):
            return codigo
    return f"RR-{random.randint(10000, 99999)}-{uuid.uuid4().hex[:3].upper()}"


def gerar_codigo_afiliado_unico():
    """Gera um código de afiliado único"""
    max_tentativas = 10
    for _ in range(max_tentativas):
        codigo = gerar_codigo_afiliado()
        if verificar_codigo_unico(codigo, 'rb_afiliados', 'rb_codigo'):
            return codigo
    return f"AF{random.randint(100000, 999999)}"


def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração do Supabase"""
    if not supabase:
        return valor_padrao
    try:
        response = supabase.table('rb_configuracoes').select('rb_valor').eq(
            'rb_chave', chave
        ).execute()
        if response.data:
            return response.data[0]['rb_valor']
        return valor_padrao
    except Exception as e:
        print(f"❌ Erro ao obter configuração {chave}: {str(e)}")
        return valor_padrao


def atualizar_configuracao(chave, valor):
    """Atualiza valor de configuração no Supabase"""
    if not supabase:
        return False
    try:
        response = supabase.table('rb_configuracoes').update({
            'rb_valor': str(valor)
        }).eq('rb_chave', chave).execute()
        return response.data is not None
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração {chave}: {str(e)}")
        return False


def obter_total_vendas():
    """Obtém total de vendas aprovadas do Supabase - FUNÇÃO CRÍTICA PARA CONTROLE"""
    if not supabase:
        return 0
    try:
        response = supabase.table('rb_vendas').select('rb_quantidade').eq(
            'rb_status', 'completed'
        ).execute()
        if response.data:
            total = sum(venda['rb_quantidade'] for venda in response.data)
            print(f"📊 Total vendas contabilizadas: {total}/{LIMITE_PREMIOS}")
            return total
        print(f"📊 Nenhuma venda encontrada: 0/{LIMITE_PREMIOS}")
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de vendas: {str(e)}")
        return 0


def sortear_premio():
    """🚫 FUNÇÃO CRÍTICA - Sorteia prêmio COM BLOQUEIO RIGOROSO ATÉ 1000 VENDAS"""
    try:
        # 🚫 VERIFICAÇÃO CRÍTICA OBRIGATÓRIA - BLOQUEIO TOTAL
        vendas_atuais = obter_total_vendas()
        sistema_liberado = vendas_atuais >= LIMITE_PREMIOS
        
        log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                           "LIBERADO" if sistema_liberado else "BLOQUEADO")
        
        # ⚠️ BLOQUEIO ABSOLUTO - NENHUM PRÊMIO ANTES DE 1000 VENDAS
        if not sistema_liberado:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               "DERROTA_FORÇADA - Sistema travado")
            return None  # FORÇA "VOCÊ PERDEU"
        
        # Sistema liberado - sortear normalmente
        print(f"🎁 Sistema liberado! Iniciando sorteio real para raspadinha...")
        
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               "Sistema desativado pelo admin")
            return None

        # Chance de ganhar configurável (apenas quando liberado)
        chance_ganhar = float(obter_configuracao('chance_ganhar', '0.15'))  # 15% padrão
        if random.random() > chance_ganhar:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               f"Sem sorte - chance {chance_ganhar*100}%")
            return None

        # Obter prêmios disponíveis
        premios = obter_premios_disponiveis()

        # Criar lista ponderada de prêmios (menor valor = maior chance)
        premios_ponderados = []
        pesos = {
            'R$ 10,00': 50, 'R$ 20,00': 30, 'R$ 30,00': 15,
            'R$ 50,00': 10, 'R$ 100,00': 5, 'R$ 300,00': 2, 
            'R$ 500,00': 1, 'R$ 1000,00': 0.5
        }

        for valor, quantidade in premios.items():
            if quantidade > 0:
                peso = int(pesos.get(valor, 1) * 10)
                premios_ponderados.extend([valor] * peso)

        if not premios_ponderados:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               "Nenhum prêmio disponível")
            return None

        # Sortear prêmio
        premio = random.choice(premios_ponderados)

        # Verificar se ainda há prêmios desse valor
        if premios[premio] <= 0:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               f"Prêmio {premio} esgotado")
            return None

        # Diminuir a quantidade do prêmio sorteado
        chave_premio = (
            f"premios_r{premio.replace('R$ ', '').replace(',00', '').replace('.', '')}"
        )
        quantidade_atual = int(obter_configuracao(chave_premio, '0'))
        if quantidade_atual > 0:
            atualizar_configuracao(chave_premio, quantidade_atual - 1)
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_PREMIO", 
                               f"PRÊMIO CONCEDIDO: {premio} - Restam: {quantidade_atual - 1}")
            return premio

        return None

    except Exception as e:
        print(f"❌ Erro ao sortear prêmio: {str(e)}")
        return None


def sortear_premio_roda():
    """🎰 FUNÇÃO CRÍTICA - Sorteia prêmio da Roda Brasil COM BLOQUEIO RIGOROSO"""
    try:
        # 🚫 VERIFICAÇÃO CRÍTICA OBRIGATÓRIA - BLOQUEIO TOTAL
        vendas_atuais = obter_total_vendas()
        sistema_liberado = vendas_atuais >= LIMITE_PREMIOS
        
        log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                           "LIBERADO" if sistema_liberado else "BLOQUEADO")
        
        # ⚠️ BLOQUEIO ABSOLUTO - SEMPRE "VOCÊ PERDEU" ANTES DE 1000 VENDAS
        if not sistema_liberado:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                               "DERROTA_FORÇADA - Sistema travado")
            return "VOCÊ PERDEU"  # FORÇA DERROTA OBRIGATÓRIA
        
        # Sistema liberado - sortear normalmente
        print(f"🎰 Sistema liberado! Iniciando sorteio real da Roda Brasil...")
        
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                               "Sistema desativado pelo admin")
            return "VOCÊ PERDEU"

        # Chance de ganhar na roda (mais generosa que raspadinhas quando liberado)
        chance_ganhar = float(obter_configuracao('chance_ganhar_roda', '0.35'))  # 35% padrão
        if random.random() > chance_ganhar:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                               f"Sem sorte - chance {chance_ganhar*100}%")
            return "VOCÊ PERDEU"

        # Obter prêmios disponíveis
        premios = obter_premios_roda_disponiveis()

        # Criar lista ponderada de prêmios
        premios_ponderados = []
        pesos = {
            'R$ 1,00': 40, 'R$ 5,00': 30, 'R$ 10,00': 20,
            'R$ 100,00': 8, 'R$ 300,00': 4, 'R$ 500,00': 2, 'R$ 1000,00': 1
        }

        for valor, quantidade in premios.items():
            if quantidade > 0:
                peso = int(pesos.get(valor, 1) * 10)
                premios_ponderados.extend([valor] * peso)

        if not premios_ponderados:
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                               "Nenhum prêmio disponível")
            return "VOCÊ PERDEU"

        # Sortear prêmio
        premio = random.choice(premios_ponderados)

        # Diminuir a quantidade do prêmio sorteado
        chave_premio = (
            f"premios_roda_r{premio.replace('R$ ', '').replace(',00', '').replace('.', '')}"
        )
        quantidade_atual = int(obter_configuracao(chave_premio, '0'))
        if quantidade_atual > 0:
            atualizar_configuracao(chave_premio, quantidade_atual - 1)
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, "SORTEAR_RODA", 
                               f"PRÊMIO CONCEDIDO: {premio} - Restam: {quantidade_atual - 1}")
            return premio

        return "VOCÊ PERDEU"

    except Exception as e:
        print(f"❌ Erro ao sortear prêmio da roda: {str(e)}")
        return "VOCÊ PERDEU"


def obter_premios_disponiveis():
    """Obtém prêmios disponíveis do Supabase"""
    try:
        premios = {
            'R$ 10,00': int(obter_configuracao('premios_r10', '100')),
            'R$ 20,00': int(obter_configuracao('premios_r20', '80')),
            'R$ 30,00': int(obter_configuracao('premios_r30', '60')),
            'R$ 50,00': int(obter_configuracao('premios_r50', '40')),
            'R$ 100,00': int(obter_configuracao('premios_r100', '25')),
            'R$ 300,00': int(obter_configuracao('premios_r300', '10')),
            'R$ 500,00': int(obter_configuracao('premios_r500', '5')),
            'R$ 1000,00': int(obter_configuracao('premios_r1000', '2'))
        }
        return premios
    except Exception as e:
        print(f"❌ Erro ao obter prêmios: {str(e)}")
        return {
            'R$ 10,00': 100, 'R$ 20,00': 80, 'R$ 30,00': 60,
            'R$ 50,00': 40, 'R$ 100,00': 25, 'R$ 300,00': 10,
            'R$ 500,00': 5, 'R$ 1000,00': 2
        }


def obter_premios_roda_disponiveis():
    """Obtém prêmios da Roda Brasil disponíveis"""
    try:
        premios = {
            'R$ 1,00': int(obter_configuracao('premios_roda_r1', '100')),
            'R$ 5,00': int(obter_configuracao('premios_roda_r5', '80')),
            'R$ 10,00': int(obter_configuracao('premios_roda_r10', '60')),
            'R$ 100,00': int(obter_configuracao('premios_roda_r100', '25')),
            'R$ 300,00': int(obter_configuracao('premios_roda_r300', '10')),
            'R$ 500,00': int(obter_configuracao('premios_roda_r500', '5')),
            'R$ 1000,00': int(obter_configuracao('premios_roda_r1000', '3'))
        }
        return premios
    except Exception as e:
        print(f"❌ Erro ao obter prêmios da roda: {str(e)}")
        return {
            'R$ 1,00': 100, 'R$ 5,00': 80, 'R$ 10,00': 60,
            'R$ 100,00': 25, 'R$ 300,00': 10, 'R$ 500,00': 5,
            'R$ 1000,00': 3
        }


def obter_total_ganhadores():
    """Obtém total de ganhadores do Supabase"""
    if not supabase:
        return 0
    try:
        response_raspa = supabase.table('rb_ganhadores').select('rb_id').execute()
        response_roda = supabase.table('rb_ganhadores_roda').select('rb_id').execute()
        
        total_raspa = len(response_raspa.data) if response_raspa.data else 0
        total_roda = len(response_roda.data) if response_roda.data else 0
        
        return total_raspa + total_roda
    except Exception as e:
        print(f"❌ Erro ao obter total de ganhadores: {str(e)}")
        return 0


def obter_total_afiliados():
    """Obtém total de afiliados ativos do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_status', 'ativo'
        ).execute()
        if response.data:
            return len(response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de afiliados: {str(e)}")
        return 0


def validar_pagamento_aprovado(payment_id):
    """Valida se o pagamento foi realmente aprovado"""
    if not sdk or not payment_id:
        return False

    try:
        payment_response = sdk.payment().get(payment_id)
        if payment_response["status"] == 200:
            payment = payment_response["response"]
            return payment['status'] == 'approved'
        return False
    except Exception as e:
        print(f"❌ Erro ao validar pagamento {payment_id}: {str(e)}")
        return False


# ========== ROTAS PRINCIPAIS ==========

@app.route('/')
def index():
    """Serve a página principal"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"""
        <h1>❌ Erro ao carregar a página</h1>
        <p>Erro: {str(e)}</p>
        <p>Verifique se o arquivo index.html está na pasta correta.</p>
        """, 500


@app.route('/health')
def health_check():
    """Health check para o Render"""
    vendas = obter_total_vendas()
    return {
        'status': 'healthy',
        'supabase': supabase is not None,
        'mercadopago': sdk is not None,
        'vendas_atuais': vendas,
        'limite_premios': LIMITE_PREMIOS,
        'sistema_liberado': vendas >= LIMITE_PREMIOS,
        'timestamp': datetime.now().isoformat()
    }


@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX real via Mercado Pago para raspadinhas"""
    data = request.json
    quantidade = data.get('quantidade', 1)
    total = quantidade * 1.00
    afiliado_codigo = data.get('ref_code') or session.get('ref_code')

    if not sdk:
        return jsonify({
            'error': 'Mercado Pago não configurado.',
            'details': 'Token do Mercado Pago necessário.'
        }), 500

    vendidas = obter_total_vendas()
    if vendidas + quantidade > TOTAL_RASPADINHAS:
        return jsonify({
            'error': 'Raspadinhas esgotadas',
            'details': (
                f'Restam apenas {TOTAL_RASPADINHAS - vendidas} disponíveis'
            )
        }), 400

    payment_data = {
        "transaction_amount": float(total),
        "description": f"Raspa Brasil - {quantidade} raspadinha(s)",
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@raspabrasil.com",
            "first_name": "Cliente",
            "last_name": "Raspa Brasil"
        },
        "notification_url": (
            f"{request.url_root.rstrip('/')}/webhook/mercadopago"
        ),
        "external_reference": (
            f"RB_{int(datetime.now().timestamp())}_{quantidade}"
        )
    }

    try:
        print(f"💳 Criando pagamento raspadinha: R$ {total:.2f} - Vendas atuais: {vendidas}")
        payment_response = sdk.payment().create(payment_data)

        if payment_response["status"] == 201:
            payment = payment_response["response"]

            session['payment_id'] = str(payment['id'])
            session['quantidade'] = quantidade
            session['payment_created_at'] = datetime.now().isoformat()

            if supabase:
                try:
                    venda_data = {
                        'rb_quantidade': quantidade,
                        'rb_valor_total': total,
                        'rb_payment_id': str(payment['id']),
                        'rb_status': 'pending',
                        'rb_tipo': 'raspadinha',
                        'rb_ip_cliente': request.remote_addr,
                        'rb_user_agent': request.headers.get(
                            'User-Agent', ''
                        )[:500]
                    }
                    
                    if afiliado_codigo:
                        # Buscar afiliado
                        afiliado_response = supabase.table('rb_afiliados').select('rb_id').eq(
                            'rb_codigo', afiliado_codigo
                        ).eq('rb_status', 'ativo').execute()
                        
                        if afiliado_response.data:
                            venda_data['rb_afiliado_id'] = afiliado_response.data[0]['rb_id']
                    
                    supabase.table('rb_vendas').insert(venda_data).execute()
                    
                except Exception as e:
                    print(f"❌ Erro ao salvar venda: {str(e)}")

            pix_data = payment.get(
                'point_of_interaction', {}
            ).get('transaction_data', {})

            if not pix_data:
                return jsonify({'error': 'Erro ao gerar dados PIX'}), 500

            return jsonify({
                'id': payment['id'],
                'qr_code': pix_data.get('qr_code', ''),
                'qr_code_base64': pix_data.get('qr_code_base64', ''),
                'status': payment['status'],
                'amount': payment['transaction_amount']
            })
        else:
            return jsonify({
                'error': 'Erro ao criar pagamento',
                'details': payment_response.get('message', 'Erro desconhecido')
            }), 500

    except Exception as e:
        print(f"❌ Exceção ao criar pagamento: {str(e)}")
        return jsonify({
            'error': 'Erro interno do servidor',
            'details': str(e)
        }), 500


@app.route('/create_payment_roda', methods=['POST'])
def create_payment_roda():
    """Cria pagamento PIX para Roda Brasil"""
    data = request.json
    quantidade = data.get('quantidade', 1)
    total = quantidade * 1.00

    if not sdk:
        return jsonify({
            'error': 'Mercado Pago não configurado.',
            'details': 'Token do Mercado Pago necessário.'
        }), 500

    payment_data = {
        "transaction_amount": float(total),
        "description": f"Roda Brasil - {quantidade} ficha(s)",
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@rodabrasil.com",
            "first_name": "Cliente",
            "last_name": "Roda Brasil"
        },
        "notification_url": (
            f"{request.url_root.rstrip('/')}/webhook/mercadopago"
        ),
        "external_reference": (
            f"RR_{int(datetime.now().timestamp())}_{quantidade}"
        )
    }

    try:
        vendas = obter_total_vendas()
        print(f"🎰 Criando pagamento Roda Brasil: R$ {total:.2f} - Vendas atuais: {vendas}")
        payment_response = sdk.payment().create(payment_data)

        if payment_response["status"] == 201:
            payment = payment_response["response"]

            session['payment_id_roda'] = str(payment['id'])
            session['quantidade_roda'] = quantidade
            session['payment_created_at_roda'] = datetime.now().isoformat()

            if supabase:
                try:
                    venda_data = {
                        'rb_quantidade': quantidade,
                        'rb_valor_total': total,
                        'rb_payment_id': str(payment['id']),
                        'rb_status': 'pending',
                        'rb_tipo': 'roda_brasil',
                        'rb_ip_cliente': request.remote_addr,
                        'rb_user_agent': request.headers.get(
                            'User-Agent', ''
                        )[:500]
                    }
                    
                    supabase.table('rb_vendas').insert(venda_data).execute()
                    
                except Exception as e:
                    print(f"❌ Erro ao salvar venda roda: {str(e)}")

            pix_data = payment.get(
                'point_of_interaction', {}
            ).get('transaction_data', {})

            if not pix_data:
                return jsonify({'error': 'Erro ao gerar dados PIX'}), 500

            return jsonify({
                'id': payment['id'],
                'qr_code': pix_data.get('qr_code', ''),
                'qr_code_base64': pix_data.get('qr_code_base64', ''),
                'status': payment['status'],
                'amount': payment['transaction_amount']
            })
        else:
            return jsonify({
                'error': 'Erro ao criar pagamento',
                'details': payment_response.get('message', 'Erro desconhecido')
            }), 500

    except Exception as e:
        print(f"❌ Exceção ao criar pagamento roda: {str(e)}")
        return jsonify({
            'error': 'Erro interno do servidor',
            'details': str(e)
        }), 500


@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verifica status do pagamento no Mercado Pago para raspadinhas"""
    if not sdk:
        return jsonify({'error': 'Mercado Pago não configurado'}), 500

    try:
        print(f"🔍 Verificando pagamento raspadinha: {payment_id}")

        payment_response = sdk.payment().get(payment_id)

        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment['status']

            print(f"📊 Status do pagamento {payment_id}: {status}")

            # Se aprovado e ainda não processado, atualizar no Supabase
            payment_key = f'payment_processed_{payment_id}'
            if status == 'approved' and payment_key not in session:
                if supabase:
                    try:
                        # Atualizar status da venda
                        supabase.table('rb_vendas').update({
                            'rb_status': 'completed'
                        }).eq('rb_payment_id', payment_id).execute()

                        # Processar comissão de afiliado se existir
                        venda_response = supabase.table('rb_vendas').select('*').eq(
                            'rb_payment_id', payment_id
                        ).execute()
                        
                        if venda_response.data and venda_response.data[0].get('rb_afiliado_id'):
                            venda = venda_response.data[0]
                            comissao = float(venda['rb_valor_total']) * (PERCENTUAL_COMISSAO_AFILIADO / 100)
                            
                            # Atualizar saldo do afiliado
                            supabase.rpc('incrementar_saldo_afiliado', {
                                'afiliado_id': venda['rb_afiliado_id'],
                                'valor_comissao': comissao,
                                'quantidade_vendas': venda['rb_quantidade']
                            }).execute()

                        session[payment_key] = True
                        
                        # Atualizar vendas totais para verificação
                        vendas_atualizadas = obter_total_vendas()
                        print(f"✅ Pagamento aprovado: {payment_id} - Total vendas: {vendas_atualizadas}")

                        # Log da mudança
                        log_payment_change(
                            payment_id, 'pending', 'completed', {
                                'source': 'check_payment',
                                'amount': payment.get('transaction_amount', 0),
                                'vendas_totais': vendas_atualizadas
                            }
                        )

                    except Exception as e:
                        print(
                            f"❌ Erro ao atualizar status no Supabase: "
                            f"{str(e)}"
                        )

            return jsonify({
                'status': status,
                'amount': payment.get('transaction_amount', 0),
                'description': payment.get('description', ''),
                'date_created': payment.get('date_created', ''),
                'date_approved': payment.get('date_approved', '')
            })
        else:
            print(f"❌ Erro ao verificar pagamento: {payment_response}")
            return jsonify({'error': 'Erro ao verificar pagamento'}), 500

    except Exception as e:
        print(f"❌ Exceção ao verificar pagamento: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/check_payment_roda/<payment_id>')
def check_payment_roda(payment_id):
    """Verifica status do pagamento da Roda Brasil"""
    if not sdk:
        return jsonify({'error': 'Mercado Pago não configurado'}), 500

    try:
        print(f"🎰 Verificando pagamento Roda: {payment_id}")

        payment_response = sdk.payment().get(payment_id)

        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment['status']

            print(f"📊 Status do pagamento Roda {payment_id}: {status}")

            # Se aprovado e ainda não processado, atualizar no Supabase
            payment_key = f'payment_roda_processed_{payment_id}'
            if status == 'approved' and payment_key not in session:
                if supabase:
                    try:
                        # Atualizar status da venda
                        supabase.table('rb_vendas').update({
                            'rb_status': 'completed'
                        }).eq('rb_payment_id', payment_id).execute()

                        session[payment_key] = True
                        
                        # Atualizar vendas totais
                        vendas_atualizadas = obter_total_vendas()
                        print(f"✅ Pagamento Roda aprovado: {payment_id} - Total vendas: {vendas_atualizadas}")

                    except Exception as e:
                        print(f"❌ Erro ao atualizar status Roda: {str(e)}")

            return jsonify({
                'status': status,
                'amount': payment.get('transaction_amount', 0),
                'description': payment.get('description', ''),
                'date_created': payment.get('date_created', ''),
                'date_approved': payment.get('date_approved', '')
            })
        else:
            return jsonify({'error': 'Erro ao verificar pagamento'}), 500

    except Exception as e:
        print(f"❌ Exceção ao verificar pagamento Roda: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/raspar', methods=['POST'])
def raspar():
    """🚫 FUNÇÃO CRÍTICA - Processa raspagem COM BLOQUEIO RIGOROSO"""
    try:
        # Verificar se há pagamento aprovado na sessão
        payment_id = session.get('payment_id')
        quantidade_paga = session.get('quantidade', 0)

        if not payment_id:
            return jsonify({
                'ganhou': False,
                'erro': 'Nenhum pagamento encontrado. Pague primeiro.'
            }), 400

        # Validar se o pagamento foi realmente aprovado
        if not validar_pagamento_aprovado(payment_id):
            return jsonify({
                'ganhou': False,
                'erro': 'Pagamento não aprovado. Aguarde confirmação.'
            }), 400

        # Verificar se ainda há raspadinhas restantes
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)

        if raspadas >= quantidade_paga:
            return jsonify({
                'ganhou': False,
                'erro': 'Todas as raspadinhas já foram utilizadas.'
            }), 400

        # Incrementar contador de raspadas
        session[raspadas_key] = raspadas + 1

        # 🚫 VERIFICAÇÃO CRÍTICA - BLOQUEIO TOTAL ATÉ 1000 VENDAS
        vendas_atuais = obter_total_vendas()
        sistema_liberado = vendas_atuais >= LIMITE_PREMIOS
        
        log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, f"RASPAR_{payment_id}", 
                           "LIBERADO" if sistema_liberado else "BLOQUEADO")

        # Tentar sortear prêmio (função já tem bloqueio interno)
        premio = sortear_premio()

        if premio:
            codigo = gerar_codigo_unico()
            print(
                f"🎉 Prêmio de raspadinha concedido: {premio} - "
                f"Código: {codigo} - Payment: {payment_id}"
            )
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo
            })
        else:
            resultado = "BLOQUEADO por limite" if not sistema_liberado else "Sem sorte"
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, f"RASPAR_{payment_id}", 
                               f"SEM PRÊMIO: {resultado}")
            return jsonify({'ganhou': False})

    except Exception as e:
        print(f"❌ Erro ao processar raspagem: {str(e)}")
        return jsonify({'ganhou': False, 'erro': str(e)}), 500


@app.route('/girar_roda', methods=['POST'])
def girar_roda():
    """🎰 FUNÇÃO CRÍTICA - Processa giro da roleta COM BLOQUEIO RIGOROSO"""
    try:
        # Verificar se há pagamento aprovado na sessão
        payment_id = session.get('payment_id_roda')
        fichas_pagas = session.get('quantidade_roda', 0)

        if not payment_id:
            return jsonify({
                'ganhou': False,
                'premio': 'VOCÊ PERDEU',
                'erro': 'Nenhum pagamento encontrado. Pague primeiro.'
            }), 400

        # Validar se o pagamento foi realmente aprovado
        if not validar_pagamento_aprovado(payment_id):
            return jsonify({
                'ganhou': False,
                'premio': 'VOCÊ PERDEU',
                'erro': 'Pagamento não aprovado. Aguarde confirmação.'
            }), 400

        # Verificar se ainda há fichas restantes
        giradas_key = f'giradas_{payment_id}'
        giradas = session.get(giradas_key, 0)

        if giradas >= fichas_pagas:
            return jsonify({
                'ganhou': False,
                'premio': 'VOCÊ PERDEU',
                'erro': 'Todas as fichas já foram utilizadas.'
            }), 400

        # Incrementar contador de giradas
        session[giradas_key] = giradas + 1

        # 🚫 VERIFICAÇÃO CRÍTICA - BLOQUEIO TOTAL ATÉ 1000 VENDAS
        vendas_atuais = obter_total_vendas()
        sistema_liberado = vendas_atuais >= LIMITE_PREMIOS
        
        log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, f"GIRAR_RODA_{payment_id}", 
                           "LIBERADO" if sistema_liberado else "BLOQUEADO")

        # Sortear prêmio da roda (função já tem bloqueio interno)
        premio = sortear_premio_roda()

        if premio != "VOCÊ PERDEU":
            codigo = gerar_codigo_unico_roda()
            print(
                f"🎰 Prêmio da roda concedido: {premio} - "
                f"Código: {codigo} - Payment: {payment_id}"
            )
            return jsonify({
                'ganhou': True,
                'premio': premio,
                'codigo': codigo
            })
        else:
            resultado = "BLOQUEADO por limite" if not sistema_liberado else "Sem sorte"
            log_sistema_bloqueio(vendas_atuais, LIMITE_PREMIOS, f"GIRAR_RODA_{payment_id}", 
                               f"SEM PRÊMIO: {resultado}")
            return jsonify({
                'ganhou': False,
                'premio': 'VOCÊ PERDEU'
            })

    except Exception as e:
        print(f"❌ Erro ao girar roda: {str(e)}")
        return jsonify({
            'ganhou': False,
            'premio': 'VOCÊ PERDEU',
            'erro': str(e)
        }), 500


@app.route('/salvar_ganhador', methods=['POST'])
def salvar_ganhador():
    """Salva dados do ganhador no Supabase"""
    if not supabase:
        return jsonify({
            'sucesso': False,
            'erro': 'Supabase não conectado'
        })

    try:
        data = request.json

        # Validar dados obrigatórios
        campos_obrigatorios = [
            'codigo', 'nome', 'valor', 'chave_pix', 'tipo_chave'
        ]
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        # Verificar se o código é válido (não foi usado antes)
        existing = supabase.table('rb_ganhadores').select('rb_id').eq(
            'rb_codigo', data['codigo']
        ).execute()
        if existing.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Código já utilizado'
            })

        response = supabase.table('rb_ganhadores').insert({
            'rb_codigo': data['codigo'],
            'rb_nome': data['nome'].strip()[:255],
            'rb_valor': data['valor'],
            'rb_chave_pix': data['chave_pix'].strip()[:255],
            'rb_tipo_chave': data['tipo_chave'],
            'rb_telefone': data.get('telefone', '')[:20],
            'rb_status_pagamento': 'pendente'
        }).execute()

        if response.data:
            print(
                f"💾 Ganhador de raspadinha salvo: {data['nome']} - "
                f"{data['valor']} - {data['codigo']}"
            )
            
            # Criar solicitação de saque automaticamente
            try:
                supabase.table('rb_saques_ganhadores').insert({
                    'rb_ganhador_id': response.data[0]['rb_id'],
                    'rb_valor': data['valor'],
                    'rb_chave_pix': data['chave_pix'],
                    'rb_tipo_chave': data['tipo_chave'],
                    'rb_status': 'solicitado'
                }).execute()
                print(f"💰 Saque automático criado para ganhador")
            except Exception as e:
                print(f"⚠️ Erro ao criar saque automático: {str(e)}")
            
            return jsonify({'sucesso': True, 'id': response.data[0]['rb_id']})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir ganhador'
            })

    except Exception as e:
        print(f"❌ Erro ao salvar ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/salvar_ganhador_roda', methods=['POST'])
def salvar_ganhador_roda():
    """Salva dados do ganhador da Roda Brasil no Supabase"""
    if not supabase:
        return jsonify({
            'sucesso': False,
            'erro': 'Supabase não conectado'
        })

    try:
        data = request.json

        # Validar dados obrigatórios
        campos_obrigatorios = [
            'codigo', 'nome', 'cpf', 'valor', 'chave_pix', 'tipo_chave'
        ]
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        # Validar CPF
        cpf = data['cpf']
        if len(cpf) != 11:
            return jsonify({
                'sucesso': False,
                'erro': 'CPF deve ter 11 dígitos'
            })

        # Verificar se o código é válido (não foi usado antes)
        existing = supabase.table('rb_ganhadores_roda').select('rb_id').eq(
            'rb_codigo', data['codigo']
        ).execute()
        if existing.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Código já utilizado'
            })

        response = supabase.table('rb_ganhadores_roda').insert({
            'rb_codigo': data['codigo'],
            'rb_nome': data['nome'].strip()[:255],
            'rb_cpf': cpf,
            'rb_valor': data['valor'],
            'rb_chave_pix': data['chave_pix'].strip()[:255],
            'rb_tipo_chave': data['tipo_chave'],
            'rb_status_pagamento': 'pendente'
        }).execute()

        if response.data:
            print(
                f"🎰 Ganhador da roda salvo: {data['nome']} - "
                f"{data['valor']} - {data['codigo']}"
            )
            
            # Criar solicitação de saque automaticamente
            try:
                supabase.table('rb_saques_ganhadores').insert({
                    'rb_ganhador_id': response.data[0]['rb_id'],
                    'rb_valor': data['valor'],
                    'rb_chave_pix': data['chave_pix'],
                    'rb_tipo_chave': data['tipo_chave'],
                    'rb_status': 'solicitado'
                }).execute()
                print(f"💰 Saque automático criado para ganhador da roda")
            except Exception as e:
                print(f"⚠️ Erro ao criar saque automático: {str(e)}")
            
            return jsonify({'sucesso': True, 'id': response.data[0]['rb_id']})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir ganhador'
            })

    except Exception as e:
        print(f"❌ Erro ao salvar ganhador da roda: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


# ========== ROTAS DE AFILIADOS ==========

@app.route('/cadastrar_afiliado', methods=['POST'])
def cadastrar_afiliado():
    """Cadastra novo afiliado"""
    if not supabase:
        return jsonify({
            'sucesso': False,
            'erro': 'Sistema indisponível'
        })

    try:
        data = request.json

        # Validar dados obrigatórios
        campos_obrigatorios = ['nome', 'email', 'telefone', 'cpf']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        # Limpar CPF
        cpf = data['cpf'].replace('.', '').replace('-', '').replace(' ', '')
        if len(cpf) != 11:
            return jsonify({
                'sucesso': False,
                'erro': 'CPF inválido'
            })

        # Verificar se email ou CPF já existe
        existing_email = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_email', data['email']
        ).execute()
        
        existing_cpf = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_cpf', cpf
        ).execute()
        
        if existing_email.data or existing_cpf.data:
            return jsonify({
                'sucesso': False,
                'erro': 'E-mail ou CPF já cadastrado'
            })

        # Gerar código único
        codigo = gerar_codigo_afiliado_unico()

        # Inserir afiliado
        response = supabase.table('rb_afiliados').insert({
            'rb_codigo': codigo,
            'rb_nome': data['nome'].strip()[:255],
            'rb_email': data['email'].strip().lower()[:255],
            'rb_telefone': data['telefone'].strip()[:20],
            'rb_cpf': cpf,
            'rb_status': 'ativo'
        }).execute()

        if response.data:
            afiliado = response.data[0]
            print(f"👥 Novo afiliado cadastrado: {data['nome']} - {codigo}")
            
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'id': afiliado['rb_id'],
                    'codigo': codigo,
                    'nome': afiliado['rb_nome'],
                    'email': afiliado['rb_email'],
                    'total_clicks': 0,
                    'total_vendas': 0,
                    'total_comissao': 0,
                    'saldo_disponivel': 0,
                    'link': f"{request.url_root}?ref={codigo}"
                }
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir afiliado'
            })

    except Exception as e:
        print(f"❌ Erro ao cadastrar afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/login_afiliado', methods=['POST'])
def login_afiliado():
    """Login do afiliado por CPF"""
    if not supabase:
        return jsonify({
            'sucesso': False,
            'erro': 'Sistema indisponível'
        })

    try:
        data = request.json
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11:
            return jsonify({
                'sucesso': False,
                'erro': 'CPF inválido'
            })

        # Buscar afiliado pelo CPF
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_cpf', cpf
        ).eq('rb_status', 'ativo').execute()
        
        if response.data:
            afiliado = response.data[0]
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'id': afiliado['rb_id'],
                    'codigo': afiliado['rb_codigo'],
                    'nome': afiliado['rb_nome'],
                    'email': afiliado['rb_email'],
                    'total_clicks': afiliado['rb_total_clicks'] or 0,
                    'total_vendas': afiliado['rb_total_vendas'] or 0,
                    'total_comissao': float(afiliado['rb_total_comissao'] or 0),
                    'saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0),
                    'chave_pix': afiliado['rb_chave_pix'],
                    'tipo_chave_pix': afiliado['rb_tipo_chave_pix']
                }
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'CPF não encontrado ou afiliado inativo'
            })

    except Exception as e:
        print(f"❌ Erro no login afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/atualizar_pix_afiliado', methods=['POST'])
def atualizar_pix_afiliado():
    """Atualiza chave PIX do afiliado"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})

    try:
        data = request.json
        codigo = data.get('codigo')
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')

        if not codigo or not chave_pix:
            return jsonify({
                'sucesso': False,
                'erro': 'Código e chave PIX são obrigatórios'
            })

        response = supabase.table('rb_afiliados').update({
            'rb_chave_pix': chave_pix,
            'rb_tipo_chave_pix': tipo_chave
        }).eq('rb_codigo', codigo).eq('rb_status', 'ativo').execute()

        if response.data:
            return jsonify({'sucesso': True})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Afiliado não encontrado'
            })

    except Exception as e:
        print(f"❌ Erro ao atualizar PIX: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/solicitar_saque_afiliado', methods=['POST'])
def solicitar_saque_afiliado():
    """Processa solicitação de saque do afiliado"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})

    try:
        data = request.json
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({
                'sucesso': False,
                'erro': 'Código do afiliado é obrigatório'
            })

        # Buscar afiliado
        afiliado_response = supabase.table('rb_afiliados').select('*').eq(
            'rb_codigo', codigo
        ).eq('rb_status', 'ativo').execute()

        if not afiliado_response.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Afiliado não encontrado'
            })

        afiliado = afiliado_response.data[0]
        saldo = float(afiliado['rb_saldo_disponivel'] or 0)
        saque_minimo = 10.0

        if saldo < saque_minimo:
            return jsonify({
                'sucesso': False,
                'erro': f'Saldo insuficiente. Mínimo: R$ {saque_minimo:.2f}'
            })

        if not afiliado['rb_chave_pix']:
            return jsonify({
                'sucesso': False,
                'erro': 'Configure sua chave PIX primeiro'
            })

        # Inserir solicitação de saque
        saque_response = supabase.table('rb_saques_afiliados').insert({
            'rb_afiliado_id': afiliado['rb_id'],
            'rb_valor': saldo,
            'rb_chave_pix': afiliado['rb_chave_pix'],
            'rb_tipo_chave': afiliado['rb_tipo_chave_pix'],
            'rb_status': 'solicitado'
        }).execute()

        if saque_response.data:
            # Zerar saldo do afiliado
            supabase.table('rb_afiliados').update({
                'rb_saldo_disponivel': 0
            }).eq('rb_id', afiliado['rb_id']).execute()

            print(f"💰 Saque solicitado: {afiliado['rb_nome']} - R$ {saldo:.2f}")

            return jsonify({
                'sucesso': True,
                'valor': saldo,
                'saque_id': saque_response.data[0]['rb_id']
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao processar saque'
            })

    except Exception as e:
        print(f"❌ Erro ao solicitar saque: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


# ========== ROTAS ADMIN ==========

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login do admin"""
    data = request.json
    senha = data.get('senha')
    
    if not senha:
        return jsonify({'success': False, 'message': 'Senha é obrigatória'})
    
    # Senha administrativa
    if senha == 'paulo10@admin':
        session['admin_logado'] = True
        return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
    
    return jsonify({'success': False, 'message': 'Senha incorreta'})


@app.route('/admin/toggle_sistema', methods=['POST'])
def toggle_sistema():
    """Alterna status do sistema"""
    if not session.get('admin_logado'):
        return jsonify({'success': False, 'mensagem': 'Acesso negado'})
    
    try:
        sistema_atual = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        novo_status = 'false' if sistema_atual else 'true'
        
        if atualizar_configuracao('sistema_ativo', novo_status):
            status_texto = 'ativado' if novo_status == 'true' else 'desativado'
            return jsonify({'success': True, 'mensagem': f'Sistema {status_texto} com sucesso'})
        else:
            return jsonify({'success': False, 'mensagem': 'Erro ao atualizar sistema'})
    except Exception as e:
        print(f"❌ Erro ao alternar sistema: {str(e)}")
        return jsonify({'success': False, 'mensagem': str(e)})


@app.route('/validar_codigo', methods=['POST'])
def validar_codigo():
    """Valida código de ganhador"""
    data = request.json
    codigo = data.get('codigo', '').strip().upper()
    
    if not codigo:
        return jsonify({'valido': False, 'mensagem': 'Código não fornecido'})
    
    if not supabase:
        return jsonify({'valido': False, 'mensagem': 'Sistema de validação indisponível'})
    
    try:
        # Verificar nas raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if response_raspa.data:
            ganhador = response_raspa.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - RASPADINHA - {ganhador["rb_nome"]} - {ganhador["rb_valor"]} - Status: {ganhador.get("rb_status_pagamento", "pendente")}'
            })
        
        # Verificar na Roda Brasil
        response_roda = supabase.table('rb_ganhadores_roda').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if response_roda.data:
            ganhador = response_roda.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - RODA BRASIL - {ganhador["rb_nome"]} - {ganhador["rb_valor"]} - Status: {ganhador.get("rb_status_pagamento", "pendente")}'
            })
        
        return jsonify({'valido': False, 'mensagem': '❌ Código não encontrado ou inválido'})
            
    except Exception as e:
        print(f"❌ Erro ao validar código: {str(e)}")
        return jsonify({'valido': False, 'mensagem': 'Erro ao validar código'})


@app.route('/admin/stats')
def admin_stats():
    """📊 FUNÇÃO CRÍTICA - Estatísticas do sistema com controle de limite"""
    try:
        vendidas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()
        afiliados = obter_total_afiliados()
        
        # ⚠️ VERIFICAÇÃO DO SISTEMA DE BLOQUEIO
        sistema_liberado = vendidas >= LIMITE_PREMIOS
        
        # Log do status atual
        log_sistema_bloqueio(vendidas, LIMITE_PREMIOS, "CONSULTA_STATS", 
                           f"Sistema {'LIBERADO' if sistema_liberado else 'BLOQUEADO'}")
        
        # Estatísticas do dia
        vendas_hoje = 0
        vendas_afiliados_hoje = 0
        if supabase:
            try:
                hoje = date.today().isoformat()
                vendas_response = supabase.table('rb_vendas').select('*').gte(
                    'rb_data_criacao', hoje + ' 00:00:00'
                ).eq('rb_status', 'completed').execute()
                
                vendas_hoje = len(vendas_response.data or [])
                vendas_afiliados_hoje = len([v for v in (vendas_response.data or []) if v.get('rb_afiliado_id')])
                
            except Exception as e:
                print(f"❌ Erro ao obter vendas do dia: {str(e)}")

        # Calcular prêmios restantes
        premios_raspa = obter_premios_disponiveis()
        premios_roda = obter_premios_roda_disponiveis()
        total_premios_restantes = sum(premios_raspa.values()) + sum(premios_roda.values())

        return jsonify({
            'vendidas': vendidas,
            'ganhadores': ganhadores,
            'afiliados': afiliados,
            'vendas_hoje': vendas_hoje,
            'vendas_afiliados_hoje': vendas_afiliados_hoje,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS - vendidas,
            'premios_restantes': total_premios_restantes,
            'limite_premios': LIMITE_PREMIOS,
            'sistema_liberado': sistema_liberado,
            'progresso_liberacao': f"{vendidas}/{LIMITE_PREMIOS}",
            'supabase_conectado': supabase is not None,
            'mercadopago_conectado': sdk is not None,
            'sistema_ativo': obter_configuracao(
                'sistema_ativo', 'true'
            ).lower() == 'true'
        })

    except Exception as e:
        print(f"❌ Erro ao obter estatísticas: {str(e)}")
        return jsonify({
            'vendidas': 0,
            'ganhadores': 0,
            'afiliados': 0,
            'vendas_hoje': 0,
            'vendas_afiliados_hoje': 0,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS,
            'premios_restantes': 0,
            'limite_premios': LIMITE_PREMIOS,
            'sistema_liberado': False,
            'progresso_liberacao': f"0/{LIMITE_PREMIOS}",
            'supabase_conectado': False,
            'mercadopago_conectado': False,
            'sistema_ativo': True
        })


@app.route('/admin/premiados')
def admin_premiados():
    """Lista de premiados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'premiados': []})
    
    try:
        # Buscar ganhadores de raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').order(
            'rb_data_criacao', desc=True
        ).limit(25).execute()
        
        # Buscar ganhadores da roda
        response_roda = supabase.table('rb_ganhadores_roda').select('*').order(
            'rb_data_criacao', desc=True
        ).limit(25).execute()
        
        premiados = []
        
        # Adicionar ganhadores de raspadinhas
        for ganhador in (response_raspa.data or []):
            ganhador['rb_tipo'] = 'RASPADINHA'
            premiados.append(ganhador)
        
        # Adicionar ganhadores da roda
        for ganhador in (response_roda.data or []):
            ganhador['rb_tipo'] = 'RODA BRASIL'
            premiados.append(ganhador)
        
        # Ordenar por data de criação
        premiados.sort(key=lambda x: x['rb_data_criacao'], reverse=True)
        
        return jsonify({'premiados': premiados[:50]})
        
    except Exception as e:
        print(f"❌ Erro ao listar premiados: {str(e)}")
        return jsonify({'premiados': []})


@app.route('/admin/afiliados')
def admin_afiliados():
    """Lista de afiliados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'afiliados': []})
    
    try:
        response = supabase.table('rb_afiliados').select('*').order(
            'rb_data_criacao', desc=True
        ).execute()
        
        afiliados = []
        for afiliado in response.data or []:
            afiliados.append({
                'id': afiliado['rb_id'],
                'codigo': afiliado['rb_codigo'],
                'nome': afiliado['rb_nome'],
                'email': afiliado['rb_email'],
                'telefone': afiliado['rb_telefone'],
                'total_clicks': afiliado['rb_total_clicks'] or 0,
                'total_vendas': afiliado['rb_total_vendas'] or 0,
                'total_comissao': float(afiliado['rb_total_comissao'] or 0),
                'saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0),
                'status': afiliado['rb_status'],
                'data_criacao': afiliado['rb_data_criacao']
            })
        
        return jsonify({'afiliados': afiliados})
    except Exception as e:
        print(f"❌ Erro ao listar afiliados: {str(e)}")
        return jsonify({'afiliados': []})


@app.route('/admin/saques_ganhadores')
def admin_saques_ganhadores():
    """Lista de saques de ganhadores para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'saques': []})
    
    try:
        # Buscar saques
        saques_response = supabase.table('rb_saques_ganhadores').select('*').order(
            'rb_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do ganhador de raspadinha
            ganhador_raspa = None
            try:
                ganhador_response = supabase.table('rb_ganhadores').select('rb_nome, rb_codigo').eq(
                    'rb_id', saque['rb_ganhador_id']
                ).execute()
                if ganhador_response.data:
                    ganhador_raspa = ganhador_response.data[0]
            except:
                pass
            
            # Buscar dados do ganhador da roda
            ganhador_roda = None
            try:
                ganhador_roda_response = supabase.table('rb_ganhadores_roda').select('rb_nome, rb_codigo').eq(
                    'rb_id', saque['rb_ganhador_id']
                ).execute()
                if ganhador_roda_response.data:
                    ganhador_roda = ganhador_roda_response.data[0]
            except:
                pass
            
            saque_completo = saque.copy()
            if ganhador_raspa:
                saque_completo['rb_ganhadores'] = ganhador_raspa
                saque_completo['rb_tipo'] = 'RASPADINHA'
            elif ganhador_roda:
                saque_completo['rb_ganhadores'] = ganhador_roda
                saque_completo['rb_tipo'] = 'RODA BRASIL'
            else:
                saque_completo['rb_ganhadores'] = {'rb_nome': 'Nome não encontrado', 'rb_codigo': 'N/A'}
                saque_completo['rb_tipo'] = 'DESCONHECIDO'
            
            saques.append(saque_completo)
        
        return jsonify({'saques': saques})
    except Exception as e:
        print(f"❌ Erro ao listar saques de ganhadores: {str(e)}")
        return jsonify({'saques': []})


@app.route('/admin/saques_afiliados')
def admin_saques_afiliados():
    """Lista de saques de afiliados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'saques': []})
    
    try:
        # Buscar saques
        saques_response = supabase.table('rb_saques_afiliados').select('*').order(
            'rb_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do afiliado
            afiliado_response = supabase.table('rb_afiliados').select('rb_nome, rb_codigo, rb_total_vendas').eq(
                'rb_id', saque['rb_afiliado_id']
            ).execute()
            
            saque_completo = saque.copy()
            if afiliado_response.data:
                saque_completo['rb_afiliados'] = afiliado_response.data[0]
            else:
                saque_completo['rb_afiliados'] = {'rb_nome': 'Nome não encontrado', 'rb_codigo': 'N/A', 'rb_total_vendas': 0}
            
            saques.append(saque_completo)
        
        return jsonify({'saques': saques})
    except Exception as e:
        print(f"❌ Erro ao listar saques de afiliados: {str(e)}")
        return jsonify({'saques': []})


# ========== ROTAS DE SAQUE ==========

@app.route('/admin/pagar_saque_ganhador/<int:saque_id>', methods=['POST'])
def pagar_saque_ganhador(saque_id):
    """Marca saque de ganhador como pago"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        response = supabase.table('rb_saques_ganhadores').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            return jsonify({"sucesso": True, "mensagem": "Saque marcado como pago"})
        else:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500


@app.route('/admin/excluir_saque_ganhador/<int:saque_id>', methods=['DELETE'])
def excluir_saque_ganhador(saque_id):
    """Exclui saque de ganhador (só se estiver pago)"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        # Verificar se está pago
        check_response = supabase.table('rb_saques_ganhadores').select('rb_status').eq(
            'rb_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['rb_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('rb_saques_ganhadores').delete().eq(
            'rb_id', saque_id
        ).execute()
        
        return jsonify({"sucesso": True, "mensagem": "Saque excluído com sucesso"})
        
    except Exception as e:
        print(f"❌ Erro ao excluir saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500


@app.route('/admin/pagar_saque_afiliado/<int:saque_id>', methods=['POST'])
def pagar_saque_afiliado(saque_id):
    """Marca saque de afiliado como pago"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        response = supabase.table('rb_saques_afiliados').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            return jsonify({"sucesso": True, "mensagem": "Saque marcado como pago"})
        else:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500


@app.route('/admin/excluir_saque_afiliado/<int:saque_id>', methods=['DELETE'])
def excluir_saque_afiliado(saque_id):
    """Exclui saque de afiliado (só se estiver pago)"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        # Verificar se está pago
        check_response = supabase.table('rb_saques_afiliados').select('rb_status').eq(
            'rb_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['rb_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('rb_saques_afiliados').delete().eq(
            'rb_id', saque_id
        ).execute()
        
        return jsonify({"sucesso": True, "mensagem": "Saque excluído com sucesso"})
        
    except Exception as e:
        print(f"❌ Erro ao excluir saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando Raspa Brasil + Roda Brasil...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"👥 Sistema de Afiliados: ✅")
    print(f"🎰 Roda Brasil: ✅")
    print(f"🚫 LIMITE CRÍTICO: {LIMITE_PREMIOS} vendas para liberar prêmios")
    print(f"📊 Sistema de bloqueio: ATIVO")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
