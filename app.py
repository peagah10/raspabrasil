import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_from_directory
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

# Configurações da aplicação
TOTAL_RASPADINHAS = 10000
PREMIOS_TOTAIS = 2000
WHATSAPP_NUMERO = "5582996092684"
PERCENTUAL_COMISSAO_AFILIADO = 50  # 50% de comissão
LIMITE_PREMIOS = 1000  # Só libera prêmios após 1000 vendas
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')  # Senha do admin

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


def log_payment_change(payment_id, status_anterior, status_novo, webhook_data=None):
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
    """Obtém total de vendas aprovadas do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('rb_vendas').select('rb_quantidade').eq(
            'rb_status', 'completed'
        ).execute()
        if response.data:
            return sum(venda['rb_quantidade'] for venda in response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de vendas: {str(e)}")
        return 0


def obter_vendas_hoje():
    """Obtém vendas de hoje"""
    if not supabase:
        return 0, 0
    try:
        hoje = date.today().isoformat()
        
        # Total de vendas hoje
        response_total = supabase.table('rb_vendas').select('rb_quantidade').eq(
            'rb_status', 'completed'
        ).gte('rb_data_criacao', hoje).execute()
        
        total_hoje = sum(v['rb_quantidade'] for v in response_total.data) if response_total.data else 0
        
        # Vendas via afiliados hoje
        response_afiliados = supabase.table('rb_vendas').select('rb_quantidade').eq(
            'rb_status', 'completed'
        ).gte('rb_data_criacao', hoje).not_.is_('rb_afiliado_id', 'null').execute()
        
        vendas_afiliados = sum(v['rb_quantidade'] for v in response_afiliados.data) if response_afiliados.data else 0
        
        return total_hoje, vendas_afiliados
    except Exception as e:
        print(f"❌ Erro ao obter vendas de hoje: {str(e)}")
        return 0, 0


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


def obter_sistema_ativo():
    """Verifica se o sistema está ativo"""
    return obter_configuracao('sistema_ativo', 'true') == 'true'


def alternar_sistema():
    """Alterna estado do sistema"""
    estado_atual = obter_sistema_ativo()
    novo_estado = 'false' if estado_atual else 'true'
    
    if atualizar_configuracao('sistema_ativo', novo_estado):
        return not estado_atual, "Sistema ativado" if not estado_atual else "Sistema desativado"
    else:
        return estado_atual, "Erro ao alterar sistema"


def obter_premios_disponiveis():
    """Obtém prêmios disponíveis do Supabase"""
    try:
        premios = {
            'R$ 10,00': int(obter_configuracao('premios_r10', '100')),
            'R$ 20,00': int(obter_configuracao('premios_r20', '50')),
            'R$ 30,00': int(obter_configuracao('premios_r30', '30')),
            'R$ 40,00': int(obter_configuracao('premios_r40', '20')),
            'R$ 50,00': int(obter_configuracao('premios_r50', '15')),
            'R$ 100,00': int(obter_configuracao('premios_r100', '10')),
            'R$ 300,00': int(obter_configuracao('premios_r300', '5')),
            'R$ 500,00': int(obter_configuracao('premios_r500', '3')),
            'R$ 1000,00': int(obter_configuracao('premios_r1000', '2'))
        }
        return premios
    except Exception as e:
        print(f"❌ Erro ao obter prêmios: {str(e)}")
        return {
            'R$ 10,00': 100,
            'R$ 20,00': 50,
            'R$ 30,00': 30,
            'R$ 40,00': 20,
            'R$ 50,00': 15,
            'R$ 100,00': 10,
            'R$ 300,00': 5,
            'R$ 500,00': 3,
            'R$ 1000,00': 2
        }


def obter_premios_roda_disponiveis():
    """Obtém prêmios da Roda Brasil disponíveis"""
    try:
        premios = {
            'R$ 1,00': int(obter_configuracao('premios_roda_r1', '50')),
            'R$ 5,00': int(obter_configuracao('premios_roda_r5', '30')),
            'R$ 10,00': int(obter_configuracao('premios_roda_r10', '20')),
            'R$ 100,00': int(obter_configuracao('premios_roda_r100', '10')),
            'R$ 300,00': int(obter_configuracao('premios_roda_r300', '5')),
            'R$ 500,00': int(obter_configuracao('premios_roda_r500', '3')),
            'R$ 1000,00': int(obter_configuracao('premios_roda_r1000', '2'))
        }
        return premios
    except Exception as e:
        print(f"❌ Erro ao obter prêmios da roda: {str(e)}")
        return {
            'R$ 1,00': 50,
            'R$ 5,00': 30,
            'R$ 10,00': 20,
            'R$ 100,00': 10,
            'R$ 300,00': 5,
            'R$ 500,00': 3,
            'R$ 1000,00': 2
        }


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
    return {
        'status': 'healthy',
        'supabase': supabase is not None,
        'mercadopago': sdk is not None,
        'timestamp': datetime.now().isoformat()
    }


# ========== ROTAS DE PAGAMENTO ==========

@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX real via Mercado Pago"""
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
        print(f"📤 Criando pagamento: R$ {total:.2f}")
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
                    
                    # Adicionar código de afiliado se existir
                    if afiliado_codigo:
                        # Buscar afiliado pelo código
                        response = supabase.table('rb_afiliados').select('rb_id').eq(
                            'rb_codigo', afiliado_codigo
                        ).execute()
                        if response.data:
                            venda_data['rb_afiliado_id'] = response.data[0]['rb_id']
                    
                    supabase.table('rb_vendas').insert(venda_data).execute()
                    print(f"💾 Venda salva - Payment ID: {payment['id']}")
                    
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
        print(f"🎰 Criando pagamento Roda Brasil: R$ {total:.2f}")
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
                    print(f"🎰 Venda da roda salva - Payment ID: {payment['id']}")
                    
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
    """Verifica status do pagamento no Mercado Pago"""
    if not sdk:
        return jsonify({'error': 'Mercado Pago não configurado'}), 500

    try:
        print(f"🔍 Verificando pagamento: {payment_id}")

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
                        response = supabase.table('rb_vendas').update({
                            'rb_status': 'completed'
                        }).eq('rb_payment_id', payment_id).execute()

                        # Buscar dados da venda para atualizar comissões de afiliados
                        venda_response = supabase.table('rb_vendas').select('*').eq(
                            'rb_payment_id', payment_id
                        ).execute()
                        
                        if venda_response.data:
                            venda = venda_response.data[0]
                            
                            # Se há afiliado, calcular comissão
                            if venda.get('rb_afiliado_id'):
                                comissao = venda['rb_valor_total'] * 0.5  # 50% de comissão
                                
                                # Buscar dados atuais do afiliado
                                afiliado_response = supabase.table('rb_afiliados').select('*').eq(
                                    'rb_id', venda['rb_afiliado_id']
                                ).execute()
                                
                                if afiliado_response.data:
                                    afiliado = afiliado_response.data[0]
                                    
                                    # Atualizar estatísticas do afiliado
                                    supabase.table('rb_afiliados').update({
                                        'rb_total_vendas': (afiliado['rb_total_vendas'] or 0) + venda['rb_quantidade'],
                                        'rb_total_comissao': float(afiliado['rb_total_comissao'] or 0) + comissao,
                                        'rb_saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0) + comissao
                                    }).eq('rb_id', venda['rb_afiliado_id']).execute()
                                    
                                    print(f"💰 Comissão de R$ {comissao:.2f} creditada ao afiliado")

                        session[payment_key] = True
                        print(f"✅ Pagamento aprovado: {payment_id}")

                        # Log da mudança
                        log_payment_change(
                            payment_id, 'pending', 'completed', {
                                'source': 'check_payment',
                                'amount': payment.get('transaction_amount', 0)
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
                        print(f"✅ Pagamento Roda aprovado: {payment_id}")

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


# ========== ROTAS DE GANHADORES ==========

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
                f"💾 Ganhador salvo: {data['nome']} - "
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


@app.route('/validar_codigo', methods=['POST'])
def validar_codigo():
    """Valida código de ganhador"""
    if not supabase:
        return jsonify({
            'valido': False,
            'mensagem': 'Sistema indisponível'
        })

    try:
        data = request.json
        codigo = data.get('codigo', '').strip()

        if not codigo:
            return jsonify({
                'valido': False,
                'mensagem': 'Digite um código válido'
            })

        # Buscar nas raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').eq(
            'rb_codigo', codigo
        ).execute()

        # Buscar na roda brasil
        response_roda = supabase.table('rb_ganhadores_roda').select('*').eq(
            'rb_codigo', codigo
        ).execute()

        if response_raspa.data:
            ganhador = response_raspa.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f"✅ Código válido! Ganhador: {ganhador['rb_nome']} - Prêmio: {ganhador['rb_valor']} - Status: {ganhador['rb_status_pagamento']} - Tipo: Raspadinha"
            })
        elif response_roda.data:
            ganhador = response_roda.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f"✅ Código válido! Ganhador: {ganhador['rb_nome']} - Prêmio: {ganhador['rb_valor']} - Status: {ganhador['rb_status_pagamento']} - Tipo: Roda Brasil"
            })
        else:
            return jsonify({
                'valido': False,
                'mensagem': 'Código não encontrado ou inválido'
            })

    except Exception as e:
        print(f"❌ Erro ao validar código: {str(e)}")
        return jsonify({
            'valido': False,
            'mensagem': 'Erro ao validar código'
        })


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
            'rb_status': 'ativo',
            'rb_total_clicks': 0,
            'rb_total_vendas': 0,
            'rb_total_comissao': 0.0,
            'rb_saldo_disponivel': 0.0
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
                    'link': f"https://raspabrasil.com/?ref={codigo}"
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
        saque_minimo = 10.00

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
                'erro': 'Erro ao criar solicitação de saque'
            })

    except Exception as e:
        print(f"❌ Erro ao solicitar saque: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/registrar_click', methods=['POST'])
def registrar_click():
    """Registra click do afiliado"""
    if not supabase:
        return jsonify({'sucesso': False})

    try:
        data = request.json
        codigo = data.get('ref_code')
        
        if not codigo:
            return jsonify({'sucesso': False})

        # Salvar código na sessão
        session['ref_code'] = codigo

        # Incrementar contador de clicks
        response = supabase.table('rb_afiliados').select('rb_id, rb_total_clicks').eq(
            'rb_codigo', codigo
        ).eq('rb_status', 'ativo').execute()
        
        if response.data:
            afiliado = response.data[0]
            novo_total = (afiliado['rb_total_clicks'] or 0) + 1
            
            supabase.table('rb_afiliados').update({
                'rb_total_clicks': novo_total
            }).eq('rb_id', afiliado['rb_id']).execute()
            
            print(f"👆 Click registrado para afiliado {codigo}: {novo_total}")

        return jsonify({'sucesso': True})

    except Exception as e:
        print(f"❌ Erro ao registrar click: {str(e)}")
        return jsonify({'sucesso': False})


# ========== ROTAS ADMINISTRATIVAS ==========

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login administrativo"""
    try:
        data = request.json
        senha = data.get('senha', '')
        
        if senha == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Senha incorreta'})
            
    except Exception as e:
        print(f"❌ Erro no login admin: {str(e)}")
        return jsonify({'success': False, 'error': 'Erro interno'})


@app.route('/admin/stats')
def admin_stats():
    """Estatísticas administrativas"""
    try:
        vendidas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()
        afiliados = obter_total_afiliados()
        vendas_hoje, vendas_afiliados_hoje = obter_vendas_hoje()
        sistema_ativo = obter_sistema_ativo()
        
        # Calcular prêmios restantes
        premios_raspa = obter_premios_disponiveis()
        premios_roda = obter_premios_roda_disponiveis()
        total_premios = sum(premios_raspa.values()) + sum(premios_roda.values())
        
        return jsonify({
            'vendidas': vendidas,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'ganhadores': ganhadores,
            'afiliados': afiliados,
            'vendas_hoje': vendas_hoje,
            'vendas_afiliados_hoje': vendas_afiliados_hoje,
            'premios_restantes': total_premios,
            'sistema_ativo': sistema_ativo,
            'limite_premios': LIMITE_PREMIOS
        })
        
    except Exception as e:
        print(f"❌ Erro ao obter stats admin: {str(e)}")
        return jsonify({
            'vendidas': 0,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'ganhadores': 0,
            'afiliados': 0,
            'vendas_hoje': 0,
            'vendas_afiliados_hoje': 0,
            'premios_restantes': 0,
            'sistema_ativo': True,
            'limite_premios': LIMITE_PREMIOS
        })


@app.route('/admin/toggle_sistema', methods=['POST'])
def admin_toggle_sistema():
    """Alterna estado do sistema"""
    try:
        if 'admin_logged' not in session:
            return jsonify({'success': False, 'mensagem': 'Não autorizado'})
            
        novo_estado, mensagem = alternar_sistema()
        return jsonify({'success': True, 'mensagem': mensagem, 'sistema_ativo': novo_estado})
        
    except Exception as e:
        print(f"❌ Erro ao alternar sistema: {str(e)}")
        return jsonify({'success': False, 'mensagem': 'Erro interno'})


@app.route('/admin/premiados')
def admin_premiados():
    """Lista premiados para administração"""
    if not supabase:
        return jsonify({'premiados': []})
        
    try:
        # Buscar ganhadores das raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').order(
            'rb_data_criacao', desc=True
        ).execute()
        
        # Buscar ganhadores da roda
        response_roda = supabase.table('rb_ganhadores_roda').select('*').order(
            'rb_data_criacao', desc=True
        ).execute()
        
        premiados = []
        
        # Processar ganhadores raspadinha
        if response_raspa.data:
            for g in response_raspa.data:
                premiados.append({
                    'rb_id': g['rb_id'],
                    'rb_codigo': g['rb_codigo'],
                    'rb_nome': g['rb_nome'],
                    'rb_valor': g['rb_valor'],
                    'rb_chave_pix': g['rb_chave_pix'],
                    'rb_tipo_chave': g['rb_tipo_chave'],
                    'rb_telefone': g.get('rb_telefone', ''),
                    'rb_status_pagamento': g.get('rb_status_pagamento', 'pendente'),
                    'tipo_jogo': 'raspadinha',
                    'rb_data_criacao': g['rb_data_criacao']
                })
        
        # Processar ganhadores roda
        if response_roda.data:
            for g in response_roda.data:
                premiados.append({
                    'rb_id': g['rb_id'],
                    'rb_codigo': g['rb_codigo'],
                    'rb_nome': g['rb_nome'],
                    'rb_cpf': g.get('rb_cpf', ''),
                    'rb_valor': g['rb_valor'],
                    'rb_chave_pix': g['rb_chave_pix'],
                    'rb_tipo_chave': g['rb_tipo_chave'],
                    'rb_status_pagamento': g.get('rb_status_pagamento', 'pendente'),
                    'tipo_jogo': 'roda_brasil',
                    'rb_data_criacao': g['rb_data_criacao']
                })
        
        # Ordenar por data
        premiados.sort(key=lambda x: x['rb_data_criacao'], reverse=True)
        
        return jsonify({'premiados': premiados})
        
    except Exception as e:
        print(f"❌ Erro ao buscar premiados: {str(e)}")
        return jsonify({'premiados': []})


@app.route('/admin/afiliados')
def admin_afiliados():
    """Lista afiliados para administração"""
    if not supabase:
        return jsonify({'afiliados': []})
        
    try:
        response = supabase.table('rb_afiliados').select('*').order(
            'rb_data_criacao', desc=True
        ).execute()
        
        afiliados = []
        if response.data:
            for a in response.data:
                afiliados.append({
                    'rb_id': a['rb_id'],
                    'rb_codigo': a['rb_codigo'],
                    'rb_nome': a['rb_nome'],
                    'rb_email': a['rb_email'],
                    'rb_telefone': a['rb_telefone'],
                    'rb_cpf': a['rb_cpf'],
                    'rb_status': a['rb_status'],
                    'rb_total_clicks': a['rb_total_clicks'] or 0,
                    'rb_total_vendas': a['rb_total_vendas'] or 0,
                    'rb_total_comissao': float(a['rb_total_comissao'] or 0),
                    'rb_saldo_disponivel': float(a['rb_saldo_disponivel'] or 0),
                    'rb_chave_pix': a.get('rb_chave_pix', ''),
                    'rb_data_criacao': a['rb_data_criacao']
                })
        
        return jsonify({'afiliados': afiliados})
        
    except Exception as e:
        print(f"❌ Erro ao buscar afiliados: {str(e)}")
        return jsonify({'afiliados': []})


@app.route('/admin/saques_ganhadores')
def admin_saques_ganhadores():
    """Lista saques de ganhadores"""
    if not supabase:
        return jsonify({'saques': []})
        
    try:
        # Buscar saques com join nos ganhadores
        response = supabase.table('rb_saques_ganhadores').select(
            '*, rb_ganhadores!inner(*)'
        ).order('rb_data_solicitacao', desc=True).execute()
        
        return jsonify({'saques': response.data or []})
        
    except Exception as e:
        print(f"❌ Erro ao buscar saques de ganhadores: {str(e)}")
        return jsonify({'saques': []})


@app.route('/admin/saques_afiliados')
def admin_saques_afiliados():
    """Lista saques de afiliados"""
    if not supabase:
        return jsonify({'saques': []})
        
    try:
        # Buscar saques com join nos afiliados
        response = supabase.table('rb_saques_afiliados').select(
            '*, rb_afiliados!inner(*)'
        ).order('rb_data_solicitacao', desc=True).execute()
        
        return jsonify({'saques': response.data or []})
        
    except Exception as e:
        print(f"❌ Erro ao buscar saques de afiliados: {str(e)}")
        return jsonify({'saques': []})


@app.route('/admin/pagar_saque_ganhador/<int:saque_id>', methods=['POST'])
def admin_pagar_saque_ganhador(saque_id):
    """Marca saque de ganhador como pago"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
    try:
        response = supabase.table('rb_saques_ganhadores').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            print(f"✅ Saque de ganhador pago: {saque_id}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/admin/excluir_saque_ganhador/<int:saque_id>', methods=['DELETE'])
def admin_excluir_saque_ganhador(saque_id):
    """Exclui saque de ganhador"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
    try:
        response = supabase.table('rb_saques_ganhadores').delete().eq('rb_id', saque_id).execute()
        
        if response.data:
            print(f"🗑️ Saque de ganhador excluído: {saque_id}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro ao excluir saque ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/admin/pagar_saque_afiliado/<int:saque_id>', methods=['POST'])
def admin_pagar_saque_afiliado(saque_id):
    """Marca saque de afiliado como pago"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
    try:
        response = supabase.table('rb_saques_afiliados').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            print(f"✅ Saque de afiliado pago: {saque_id}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/admin/excluir_saque_afiliado/<int:saque_id>', methods=['DELETE'])
def admin_excluir_saque_afiliado(saque_id):
    """Exclui saque de afiliado"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
    try:
        # Buscar dados do saque para devolver valor
        saque_response = supabase.table('rb_saques_afiliados').select('*').eq('rb_id', saque_id).execute()
        
        if saque_response.data:
            saque = saque_response.data[0]
            
            # Se saque ainda não foi pago, devolver valor ao afiliado
            if saque['rb_status'] == 'solicitado':
                afiliado_response = supabase.table('rb_afiliados').select('rb_saldo_disponivel').eq(
                    'rb_id', saque['rb_afiliado_id']
                ).execute()
                
                if afiliado_response.data:
                    saldo_atual = float(afiliado_response.data[0]['rb_saldo_disponivel'] or 0)
                    novo_saldo = saldo_atual + float(saque['rb_valor'])
                    
                    supabase.table('rb_afiliados').update({
                        'rb_saldo_disponivel': novo_saldo
                    }).eq('rb_id', saque['rb_afiliado_id']).execute()
                    
                    print(f"💰 Valor devolvido ao afiliado: R$ {saque['rb_valor']}")
            
            # Excluir saque
            response = supabase.table('rb_saques_afiliados').delete().eq('rb_id', saque_id).execute()
            
            if response.data:
                print(f"🗑️ Saque de afiliado excluído: {saque_id}")
                return jsonify({'sucesso': True})
            
        return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro ao excluir saque afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


# ========== ROTAS DE INFORMAÇÕES ==========

@app.route('/stats')
def get_stats():
    """Retorna estatísticas do sistema"""
    try:
        vendas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()
        afiliados = obter_total_afiliados()
        
        return jsonify({
            'total_vendas': vendas,
            'total_ganhadores': ganhadores,
            'total_afiliados': afiliados,
            'raspadinhas_restantes': max(0, TOTAL_RASPADINHAS - vendas),
            'premios_liberados': vendas >= LIMITE_PREMIOS
        })
    except Exception as e:
        print(f"❌ Erro ao obter estatísticas: {str(e)}")
        return jsonify({
            'total_vendas': 0,
            'total_ganhadores': 0,
            'total_afiliados': 0,
            'raspadinhas_restantes': TOTAL_RASPADINHAS,
            'premios_liberados': False
        })


@app.route('/premios')
def get_premios():
    """Retorna prêmios disponíveis"""
    try:
        premios_raspa = obter_premios_disponiveis()
        premios_roda = obter_premios_roda_disponiveis()
        
        return jsonify({
            'raspadinha': premios_raspa,
            'roda_brasil': premios_roda
        })
    except Exception as e:
        print(f"❌ Erro ao obter prêmios: {str(e)}")
        return jsonify({
            'raspadinha': {},
            'roda_brasil': {}
        })


# ========== WEBHOOK ==========

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago para notificações de pagamento"""
    try:
        data = request.json
        print(f"📨 Webhook recebido: {data}")

        # Verificar se é notificação de pagamento
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            
            if payment_id:
                # Buscar detalhes do pagamento
                if sdk:
                    payment_response = sdk.payment().get(payment_id)
                    
                    if payment_response["status"] == 200:
                        payment = payment_response["response"]
                        status = payment['status']
                        
                        print(f"💳 Webhook - Payment {payment_id}: {status}")
                        
                        # Se aprovado, atualizar no banco
                        if status == 'approved' and supabase:
                            try:
                                # Buscar venda pelo payment_id
                                venda_response = supabase.table('rb_vendas').select('*').eq(
                                    'rb_payment_id', str(payment_id)
                                ).execute()
                                
                                if venda_response.data:
                                    venda = venda_response.data[0]
                                    
                                    # Atualizar status se ainda não foi processado
                                    if venda['rb_status'] != 'completed':
                                        supabase.table('rb_vendas').update({
                                            'rb_status': 'completed'
                                        }).eq('rb_payment_id', str(payment_id)).execute()
                                        
                                        # Processar comissão de afiliado se existir
                                        if venda.get('rb_afiliado_id'):
                                            comissao = venda['rb_valor_total'] * (PERCENTUAL_COMISSAO_AFILIADO / 100)
                                            
                                            # Buscar dados atuais do afiliado
                                            afiliado_response = supabase.table('rb_afiliados').select('*').eq(
                                                'rb_id', venda['rb_afiliado_id']
                                            ).execute()
                                            
                                            if afiliado_response.data:
                                                afiliado = afiliado_response.data[0]
                                                
                                                # Atualizar estatísticas do afiliado
                                                supabase.table('rb_afiliados').update({
                                                    'rb_total_vendas': (afiliado['rb_total_vendas'] or 0) + venda['rb_quantidade'],
                                                    'rb_total_comissao': float(afiliado['rb_total_comissao'] or 0) + comissao,
                                                    'rb_saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0) + comissao
                                                }).eq('rb_id', venda['rb_afiliado_id']).execute()
                                                
                                                print(f"💰 Comissão processada: R$ {comissao:.2f}")
                                        
                                        # Log da mudança
                                        log_payment_change(
                                            str(payment_id), 
                                            venda['rb_status'], 
                                            'completed', 
                                            data
                                        )
                                        
                                        print(f"✅ Venda processada via webhook: {payment_id}")
                                
                            except Exception as e:
                                print(f"❌ Erro ao processar webhook: {str(e)}")
                
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        print(f"❌ Erro no webhook: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    print("🚀 Iniciando Raspa Brasil...")
    print(f"📊 Total de raspadinhas: {TOTAL_RASPADINHAS:,}")
    print(f"🎁 Total de prêmios: {PREMIOS_TOTAIS:,}")
    print(f"🔓 Prêmios liberados após: {LIMITE_PREMIOS:,} vendas")
    print(f"💰 Comissão de afiliados: {PERCENTUAL_COMISSAO_AFILIADO}%")
    print(f"📱 WhatsApp: {WHATSAPP_NUMERO}")
    print(f"🔐 Senha admin: {ADMIN_PASSWORD}")
    print(f"🔗 Supabase: {'✅ Conectado' if supabase else '❌ Desconectado'}")
    print(f"💳 Mercado Pago: {'✅ Configurado' if sdk else '❌ Não configurado'}")
    
    # Configuração para produção
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
