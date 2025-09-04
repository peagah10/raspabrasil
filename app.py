import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_from_directory, Response
from dotenv import load_dotenv
import json
import traceback
import base64
import io

# Inicializar Supabase
try:
    from supabase import create_client, Client
    supabase_available = True
except ImportError:
    supabase_available = False
    print("⚠️ Supabase não disponível - usando modo simulação")

try:
    import mercadopago
    mercadopago_available = True
except ImportError:
    mercadopago_available = False
    print("⚠️ MercadoPago não disponível - usando pagamentos simulados")

try:
    import qrcode
    qrcode_available = True
except ImportError:
    qrcode_available = False
    print("⚠️ QRCode não disponível")

import uuid

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv('SECRET_KEY', 'ganha-brasil-2024-super-secret-key')

# Configurações do Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', "https://ngishqxtnkgvognszyep.supabase.co")
SUPABASE_KEY = os.getenv('SUPABASE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5naXNocXh0bmtndm9nbnN6eWVwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI1OTMwNjcsImV4cCI6MjA2ODE2OTA2N30.FOksPjvS2NyO6dcZ_j0Grj3Prn9OP_udSGQwswtFBXE")

# Configurações do Mercado Pago
MP_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
sdk = None

# Configurações da aplicação
TOTAL_RASPADINHAS = 10000
PREMIOS_TOTAIS = 2000
WHATSAPP_NUMERO = "5582996092684"
PERCENTUAL_COMISSAO_AFILIADO = 50
PREMIO_INICIAL_ML = 1000.00
PRECO_BILHETE_ML = 2.00
PRECO_RASPADINHA_RB = 1.00
ADMIN_PASSWORD = "paulo10@admin"
APP_VERSION = "2.2.0"

# Sistema de armazenamento em memória (fallback quando Supabase não estiver disponível)
memory_storage = {
    'vendas_rb': [],
    'vendas_ml': [],
    'ganhadores_rb': [],
    'ganhadores_ml': [],
    'afiliados': [],
    'saques': [],
    'configuracoes': {
        'sistema_ativo': 'true',
        'premio_manual_liberado': '',
        'premio_acumulado': str(PREMIO_INICIAL_ML),
        'percentual_comissao_afiliado': str(PERCENTUAL_COMISSAO_AFILIADO)
    },
    'sorteios_ml': [],
    'clientes_ml': [],
    'logs': []
}

# Inicializar cliente Supabase
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Testar conexão
        test_response = supabase.table('br_vendas').select('br_id').limit(1).execute()
        print("✅ Supabase conectado e testado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao conectar com Supabase: {str(e)}")
        print("📝 Usando sistema de armazenamento em memória")
        supabase = None

# Configurar Mercado Pago
try:
    if MP_ACCESS_TOKEN and mercadopago_available:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        print("✅ Mercado Pago SDK configurado com sucesso")
    else:
        print("❌ Token do Mercado Pago não encontrado - usando pagamentos simulados")
except Exception as e:
    print(f"❌ Erro ao configurar Mercado Pago: {str(e)}")
    print("📝 Usando sistema de pagamentos simulado")

# ========== FUNÇÕES AUXILIARES ==========

def log_error(operation, error, extra_data=None):
    """Log de erros centralizado"""
    error_msg = f"❌ [{operation}] {str(error)}"
    print(error_msg)
    if extra_data:
        print(f"   Dados extras: {extra_data}")
    
    log_entry = {
        'id': len(memory_storage['logs']) + 1,
        'operacao': operation,
        'erro': str(error)[:500],
        'dados_extras': json.dumps(extra_data) if extra_data else None,
        'timestamp': datetime.now().isoformat()
    }
    
    if supabase:
        try:
            supabase.table('br_logs_sistema').insert({
                'br_operacao': operation,
                'br_erro': str(error)[:500],
                'br_dados_extras': json.dumps(extra_data) if extra_data else None,
                'br_timestamp': datetime.now().isoformat()
            }).execute()
        except:
            pass
    else:
        memory_storage['logs'].append(log_entry)

def log_info(operation, message, extra_data=None):
    """Log de informações centralizado"""
    info_msg = f"ℹ️ [{operation}] {message}"
    print(info_msg)
    if extra_data:
        print(f"   Dados: {extra_data}")

def gerar_codigo_antifraude():
    """Gera código único no formato RB-XXXXX-YYY"""
    numero = random.randint(10000, 99999)
    letras = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"RB-{numero}-{letras}"

def gerar_codigo_afiliado():
    """Gera código único para afiliado no formato AF-XXXXX"""
    numero = random.randint(100000, 999999)
    return f"AF{numero}"

def gerar_milhar():
    """Gera número aleatório de 4 dígitos entre 1111 e 9999"""
    return random.randint(1111, 9999)

def gerar_payment_id():
    """Gera ID de pagamento simulado"""
    return f"PAY_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"

def gerar_qr_code_simulado(payment_data):
    """Gera QR code simulado para pagamentos"""
    qr_text = f"PIX{payment_data['amount']:.2f}GANHA_BRASIL"
    
    if qrcode_available:
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_text)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Converter para base64
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            
            return {
                'qr_code': qr_text,
                'qr_code_base64': img_base64
            }
        except Exception as e:
            log_error("gerar_qr_code_simulado", e)
    
    # Fallback sem QR code visual
    return {
        'qr_code': qr_text,
        'qr_code_base64': None
    }

def sanitizar_dados_entrada(data):
    """Sanitiza dados de entrada para evitar problemas de segurança"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()[:500]
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, str):
        return data.strip()[:500]
    return data

def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração"""
    if supabase:
        try:
            response = supabase.table('br_configuracoes').select('br_valor').eq('br_chave', chave).execute()
            if response.data:
                return response.data[0]['br_valor']
            
            response = supabase.table('ml_configuracoes').select('ml_valor').eq('ml_chave', chave).execute()
            if response.data:
                return response.data[0]['ml_valor']
            
            return valor_padrao
        except Exception as e:
            log_error("obter_configuracao", e, {"chave": chave})
            return valor_padrao
    else:
        return memory_storage['configuracoes'].get(chave, valor_padrao)

def atualizar_configuracao(chave, valor, game_type='raspa_brasil'):
    """Atualiza valor de configuração"""
    if supabase:
        try:
            tabela = 'br_configuracoes' if game_type == 'raspa_brasil' else 'ml_configuracoes'
            campo_chave = 'br_chave' if game_type == 'raspa_brasil' else 'ml_chave'
            campo_valor = 'br_valor' if game_type == 'raspa_brasil' else 'ml_valor'
            
            response = supabase.table(tabela).update({
                campo_valor: str(valor)
            }).eq(campo_chave, chave).execute()
            
            if not response.data:
                response = supabase.table(tabela).insert({
                    campo_chave: chave,
                    campo_valor: str(valor)
                }).execute()
            
            log_info("atualizar_configuracao", f"{chave} = {valor} em {tabela}")
            return response.data is not None
        except Exception as e:
            log_error("atualizar_configuracao", e, {"chave": chave, "valor": valor})
            return False
    else:
        memory_storage['configuracoes'][chave] = str(valor)
        log_info("atualizar_configuracao", f"{chave} = {valor} (memoria)")
        return True

def validar_session_admin():
    """Valida se o usuário está logado como admin"""
    return session.get('admin_logado', False)

def obter_total_vendas(game_type='raspa_brasil'):
    """Obtém total de vendas aprovadas"""
    if supabase:
        try:
            tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
            campo_quantidade = 'br_quantidade' if game_type == 'raspa_brasil' else 'ml_quantidade'
            campo_status = 'br_status' if game_type == 'raspa_brasil' else 'ml_status'
            
            response = supabase.table(tabela).select(campo_quantidade).eq(campo_status, 'completed').execute()
            if response.data:
                total = sum(venda[campo_quantidade] for venda in response.data)
                return total
            return 0
        except Exception as e:
            log_error("obter_total_vendas", e, {"game_type": game_type})
            return 0
    else:
        vendas_key = f'vendas_{game_type.split("_")[0]}' if "_" in game_type else f'vendas_{game_type}'
        vendas = memory_storage.get(vendas_key, [])
        total = sum(v['quantidade'] for v in vendas if v.get('status') == 'completed')
        return total

def sortear_premio_novo_sistema():
    """Sistema de prêmios manual - Só libera quando admin autorizar"""
    try:
        sistema_ativo = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        if not sistema_ativo:
            log_info("sortear_premio_novo_sistema", "Sistema desativado pelo admin")
            return None

        premio_manual = obter_configuracao('premio_manual_liberado', '')
        if premio_manual:
            atualizar_configuracao('premio_manual_liberado', '')
            log_info("sortear_premio_novo_sistema", f"Prêmio manual liberado: {premio_manual}")
            return premio_manual

        log_info("sortear_premio_novo_sistema", "Nenhum prêmio liberado pelo admin")
        return None

    except Exception as e:
        log_error("sortear_premio_novo_sistema", e)
        return None

def obter_premio_acumulado():
    """Obtém valor do prêmio acumulado atual do 2 para 1000"""
    valor = obter_configuracao('premio_acumulado', str(PREMIO_INICIAL_ML))
    try:
        return float(valor)
    except:
        return PREMIO_INICIAL_ML

def verificar_raspadinhas_para_pagamento():
    """Verifica se há raspadinhas disponíveis para este pagamento específico"""
    try:
        payment_id = session.get('payment_id')
        if not payment_id or payment_id in ['undefined', 'null', '']:
            return False
            
        # Validar status do pagamento
        if supabase:
            try:
                response = supabase.table('br_vendas').select('*').eq('br_payment_id', str(payment_id)).execute()
                if not response.data or response.data[0].get('br_status') != 'completed':
                    return False
            except:
                return False
        else:
            # Verificar no armazenamento em memória
            payment_found = False
            for venda in memory_storage['vendas_rb']:
                if venda.get('payment_id') == payment_id and venda.get('status') == 'completed':
                    payment_found = True
                    break
            if not payment_found:
                return False
            
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)
        quantidade_paga = session.get('quantidade', 0)
        
        quantidade_disponivel = quantidade_paga
        if quantidade_paga == 10:
            quantidade_disponivel = 12  # Promoção 10+2
        
        disponivel = raspadas < quantidade_disponivel
        log_info("verificar_raspadinhas_para_pagamento", 
                f"Payment: {payment_id}, Raspadas: {raspadas}/{quantidade_disponivel}, Disponível: {disponivel}")
        
        return disponivel
    except Exception as e:
        log_error("verificar_raspadinhas_para_pagamento", e)
        return False

# ========== ROTAS PRINCIPAIS ==========

@app.route('/')
def index():
    """Serve a página principal"""
    try:
        # Registrar código de afiliado se presente
        ref_code = request.args.get('ref')
        if ref_code:
            session['ref_code'] = ref_code
            log_info("index", f"Código de afiliado registrado: {ref_code}")
        
        # Servir o arquivo index.html
        return send_from_directory('.', 'index.html')
    except Exception as e:
        log_error("index", e)
        return f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GANHA BRASIL - Erro</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: linear-gradient(135deg, #00b341, #ffd700); }}
                .error {{ color: #dc2626; background: white; padding: 30px; border-radius: 15px; margin: 20px auto; max-width: 500px; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h1>🚫 Erro ao carregar a página</h1>
                <p>Desculpe, ocorreu um erro temporário.</p>
                <p><a href="/" style="color: #00b341; text-decoration: none; font-weight: bold;">🔄 Tentar novamente</a></p>
            </div>
        </body>
        </html>
        """, 500

@app.route('/health')
def health_check():
    """Health check detalhado"""
    try:
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'services': {
                'supabase': supabase is not None,
                'mercadopago': sdk is not None,
                'flask': True,
                'qrcode': qrcode_available
            },
            'games': ['raspa_brasil', '2para1000'],
            'features': [
                'afiliados', 
                'admin', 
                'pagamentos_unificados', 
                'sistema_manual_premios',
                'storage_fallback',
                'qr_code_generation'
            ],
            'configuration': {
                'total_raspadinhas': TOTAL_RASPADINHAS,
                'premio_inicial_ml': PREMIO_INICIAL_ML,
                'preco_raspadinha': PRECO_RASPADINHA_RB,
                'preco_bilhete': PRECO_BILHETE_ML,
                'comissao_afiliado': PERCENTUAL_COMISSAO_AFILIADO
            }
        }
    except Exception as e:
        log_error("health_check", e)
        return {'status': 'error', 'error': str(e)}, 500

# ========== ROTAS DE PAGAMENTO ==========

@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX - Real ou Simulado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        quantidade = data.get('quantidade', 1)
        game_type = data.get('game_type', 'raspa_brasil')
        afiliado_codigo = data.get('ref_code') or session.get('ref_code')

        # Validações
        if not isinstance(quantidade, int) or quantidade < 1 or quantidade > 50:
            return jsonify({'error': 'Quantidade inválida'}), 400

        if game_type not in ['raspa_brasil', '2para1000']:
            return jsonify({'error': 'Tipo de jogo inválido'}), 400

        # Calcular preço
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        total = quantidade * preco_unitario

        log_info("create_payment", f"Criando pagamento: {game_type} - {quantidade} unidades - R$ {total:.2f}")

        # Verificar disponibilidade (apenas para Raspa Brasil)
        if game_type == 'raspa_brasil':
            vendidas = obter_total_vendas('raspa_brasil')
            if vendidas + quantidade > TOTAL_RASPADINHAS:
                return jsonify({
                    'error': 'Raspadinhas esgotadas',
                    'details': f'Restam apenas {TOTAL_RASPADINHAS - vendidas} disponíveis'
                }), 400

        # Buscar afiliado se houver código
        afiliado_id = None
        if afiliado_codigo:
            if supabase:
                try:
                    response = supabase.table('br_afiliados').select('*').eq('br_codigo', afiliado_codigo).eq('br_status', 'ativo').execute()
                    if response.data:
                        afiliado_id = response.data[0]['br_id']
                        log_info("create_payment", f"Venda com afiliado: {response.data[0]['br_nome']}")
                except Exception as e:
                    log_error("create_payment", e, {"afiliado_codigo": afiliado_codigo})
            else:
                # Buscar no armazenamento em memória
                for afiliado in memory_storage['afiliados']:
                    if afiliado.get('codigo') == afiliado_codigo and afiliado.get('status') == 'ativo':
                        afiliado_id = afiliado['id']
                        log_info("create_payment", f"Venda com afiliado: {afiliado['nome']}")
                        break

        # Descrição do pagamento
        if game_type == 'raspa_brasil':
            descricao = f"Raspa Brasil - {quantidade} raspadinha(s)"
            if quantidade == 10:
                descricao = "Raspa Brasil - 10 raspadinhas (+2 GRÁTIS!)"
        else:
            descricao = f"2 para 1000 - {quantidade} bilhete(s)"

        payment_id = None
        qr_data = {}

        # Tentar pagamento real primeiro
        if sdk:
            try:
                payment_data = {
                    "transaction_amount": float(total),
                    "description": descricao,
                    "payment_method_id": "pix",
                    "payer": {
                        "email": "cliente@ganhabrasil.com",
                        "first_name": "Cliente",
                        "last_name": "Ganha Brasil"
                    },
                    "notification_url": f"{request.url_root.rstrip('/')}/webhook/mercadopago",
                    "external_reference": f"{game_type.upper()}_{int(datetime.now().timestamp())}_{quantidade}"
                }

                payment_response = sdk.payment().create(payment_data)

                if payment_response["status"] == 201:
                    payment = payment_response["response"]
                    payment_id = str(payment['id'])
                    
                    pix_data = payment.get('point_of_interaction', {}).get('transaction_data', {})
                    qr_data = {
                        'qr_code': pix_data.get('qr_code', ''),
                        'qr_code_base64': pix_data.get('qr_code_base64', '')
                    }
                    log_info("create_payment", f"Pagamento real criado: {payment_id}")
                else:
                    raise Exception("Erro na resposta do Mercado Pago")
                    
            except Exception as e:
                log_error("create_payment_real", e)
                payment_id = None

        # Fallback para pagamento simulado
        if not payment_id:
            payment_id = gerar_payment_id()
            qr_data = gerar_qr_code_simulado({'amount': total, 'description': descricao})
            log_info("create_payment", f"Pagamento simulado criado: {payment_id}")

        # Salvar sessão
        session['payment_id'] = payment_id
        session['quantidade'] = quantidade
        session['game_type'] = game_type
        session['payment_created_at'] = datetime.now().isoformat()
        if afiliado_id:
            session['afiliado_id'] = afiliado_id

        # Salvar no banco/memória
        venda_data = {
            'payment_id': payment_id,
            'quantidade': quantidade,
            'valor_total': total,
            'status': 'pending',
            'game_type': game_type,
            'afiliado_id': afiliado_id,
            'ip_cliente': request.remote_addr or 'unknown',
            'data_criacao': datetime.now().isoformat()
        }

        if game_type == 'raspa_brasil':
            venda_data['raspadinhas_usadas'] = 0

        if supabase:
            try:
                tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
                
                if game_type == 'raspa_brasil':
                    db_data = {
                        'br_quantidade': quantidade,
                        'br_valor_total': total,
                        'br_payment_id': payment_id,
                        'br_status': 'pending',
                        'br_ip_cliente': request.remote_addr or 'unknown',
                        'br_user_agent': request.headers.get('User-Agent', '')[:500],
                        'br_raspadinhas_usadas': 0
                    }
                    if afiliado_id:
                        db_data['br_afiliado_id'] = afiliado_id
                        db_data['br_comissao_paga'] = 0
                else:
                    db_data = {
                        'ml_quantidade': quantidade,
                        'ml_valor_total': total,
                        'ml_payment_id': payment_id,
                        'ml_status': 'pending',
                        'ml_ip_cliente': request.remote_addr or 'unknown'
                    }
                    if afiliado_id:
                        db_data['ml_afiliado_id'] = afiliado_id
                
                supabase.table(tabela).insert(db_data).execute()
                log_info("create_payment", f"Venda salva no Supabase: {payment_id}")
                
            except Exception as e:
                log_error("create_payment_save", e, {"payment_id": payment_id})
        else:
            # Salvar em memória
            vendas_key = 'vendas_rb' if game_type == 'raspa_brasil' else 'vendas_ml'
            venda_data['id'] = len(memory_storage[vendas_key]) + 1
            memory_storage[vendas_key].append(venda_data)
            log_info("create_payment", f"Venda salva em memória: {payment_id}")

        return jsonify({
            'id': payment_id,
            'qr_code': qr_data.get('qr_code', ''),
            'qr_code_base64': qr_data.get('qr_code_base64', ''),
            'status': 'pending',
            'amount': total
        })

    except Exception as e:
        log_error("create_payment", e)
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verifica status do pagamento"""
    try:
        if not payment_id or payment_id in ['undefined', 'null', '']:
            return jsonify({'error': 'Payment ID inválido'}), 400

        log_info("check_payment", f"Verificando pagamento: {payment_id}")

        # Verificar pagamento real primeiro
        if sdk:
            try:
                payment_response = sdk.payment().get(str(payment_id))
                if payment_response["status"] == 200:
                    payment = payment_response["response"]
                    status = payment['status']
                    
                    # Processar aprovação
                    if status == 'approved':
                        processar_pagamento_aprovado(payment_id)
                    
                    return jsonify({
                        'status': status,
                        'amount': payment.get('transaction_amount', 0),
                        'description': payment.get('description', ''),
                        'date_created': payment.get('date_created', ''),
                        'date_approved': payment.get('date_approved', '')
                    })
            except Exception as e:
                log_error("check_payment_real", e, {"payment_id": payment_id})

        # Pagamento simulado - aprovar automaticamente após 3 segundos
        payment_key = f'payment_processed_{payment_id}'
        if payment_key not in session:
            payment_created = session.get('payment_created_at')
            if payment_created:
                created_time = datetime.fromisoformat(payment_created)
                if (datetime.now() - created_time).total_seconds() > 3:
                    # Simular aprovação
                    session[payment_key] = True
                    processar_pagamento_aprovado(payment_id)
                    log_info("check_payment", f"Pagamento simulado aprovado: {payment_id}")
                    return jsonify({'status': 'approved'})
                else:
                    return jsonify({'status': 'pending'})
            else:
                return jsonify({'status': 'pending'})
        else:
            return jsonify({'status': 'approved'})

    except Exception as e:
        log_error("check_payment", e, {"payment_id": payment_id})
        return jsonify({'error': str(e)}), 500

def processar_pagamento_aprovado(payment_id):
    """Processa pagamento aprovado"""
    try:
        game_type = session.get('game_type', 'raspa_brasil')
        
        # Atualizar no banco
        if supabase:
            try:
                tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
                campo_payment = 'br_payment_id' if game_type == 'raspa_brasil' else 'ml_payment_id'
                campo_status = 'br_status' if game_type == 'raspa_brasil' else 'ml_status'
                
                update_data = {campo_status: 'completed'}
                
                supabase.table(tabela).update(update_data).eq(campo_payment, str(payment_id)).execute()
                log_info("processar_pagamento_aprovado", f"Status atualizado no Supabase: {payment_id}")
                
            except Exception as e:
                log_error("processar_pagamento_aprovado", e, {"payment_id": payment_id})
        else:
            # Atualizar em memória
            vendas_key = 'vendas_rb' if game_type == 'raspa_brasil' else 'vendas_ml'
            for venda in memory_storage[vendas_key]:
                if venda.get('payment_id') == payment_id:
                    venda['status'] = 'completed'
                    log_info("processar_pagamento_aprovado", f"Status atualizado em memória: {payment_id}")
                    break

    except Exception as e:
        log_error("processar_pagamento_aprovado", e, {"payment_id": payment_id})

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago"""
    try:
        data = request.json
        log_info("webhook_mercadopago", f"Webhook recebido: {data}")
        
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            if payment_id:
                log_info("webhook_mercadopago", f"Processando payment: {payment_id}")
                processar_pagamento_aprovado(str(payment_id))
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        log_error("webhook_mercadopago", e)
        return jsonify({'error': 'webhook_error'}), 500

# ========== ROTAS RASPA BRASIL ==========

@app.route('/raspar', methods=['POST'])
def raspar():
    """Processa raspagem"""
    try:
        if not verificar_raspadinhas_para_pagamento():
            return jsonify({
                'ganhou': False,
                'erro': 'Pagamento não encontrado ou não aprovado. Pague primeiro para jogar.'
            }), 400

        payment_id = session.get('payment_id')
        quantidade_paga = session.get('quantidade', 0)
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)

        # Calcular quantidade máxima (incluindo bônus 10+2)
        quantidade_maxima = quantidade_paga
        if quantidade_paga == 10:
            quantidade_maxima = 12

        # Verificar se ainda pode raspar
        if raspadas >= quantidade_maxima:
            return jsonify({
                'ganhou': False,
                'erro': 'Todas as raspadinhas já foram utilizadas.'
            }), 400

        # Incrementar contador
        session[raspadas_key] = raspadas + 1

        # Atualizar contador no banco
        if supabase:
            try:
                supabase.table('br_vendas').update({
                    'br_raspadinhas_usadas': raspadas + 1
                }).eq('br_payment_id', str(payment_id)).execute()
                log_info("raspar", f"Contador atualizado: {raspadas + 1}/{quantidade_maxima}")
            except Exception as e:
                log_error("raspar", e, {"payment_id": payment_id})

        # Verificar se há prêmio liberado pelo admin
        premio = sortear_premio_novo_sistema()

        if premio:
            codigo = gerar_codigo_antifraude()
            log_info("raspar", f"PRÊMIO LIBERADO: {premio} - Código: {codigo}")
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo
            })
        else:
            log_info("raspar", f"Sem prêmio - Raspada: {raspadas + 1}/{quantidade_maxima}")
            return jsonify({'ganhou': False})

    except Exception as e:
        log_error("raspar", e)
        return jsonify({'ganhou': False, 'erro': 'Erro interno do servidor'}), 500

@app.route('/salvar_ganhador', methods=['POST'])
def salvar_ganhador():
    """Salva dados do ganhador"""
    try:
        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['codigo', 'nome', 'valor', 'chave_pix', 'tipo_chave']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'sucesso': False, 'erro': f'Campo {campo} é obrigatório'})

        # Validações
        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        if len(data['chave_pix']) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})

        ganhador_data = {
            'codigo': data['codigo'],
            'nome': data['nome'].strip()[:255],
            'valor': data['valor'],
            'chave_pix': data['chave_pix'].strip()[:255],
            'tipo_chave': data['tipo_chave'],
            'telefone': data.get('telefone', '')[:20],
            'status_pagamento': 'pendente',
            'ip_cliente': request.remote_addr or 'unknown',
            'data_criacao': datetime.now().isoformat()
        }

        if supabase:
            try:
                # Verificar se código já foi usado
                existing = supabase.table('br_ganhadores').select('br_id').eq('br_codigo', data['codigo']).execute()
                if existing.data:
                    return jsonify({'sucesso': False, 'erro': 'Código já utilizado'})

                response = supabase.table('br_ganhadores').insert({
                    'br_codigo': data['codigo'],
                    'br_nome': data['nome'].strip()[:255],
                    'br_valor': data['valor'],
                    'br_chave_pix': data['chave_pix'].strip()[:255],
                    'br_tipo_chave': data['tipo_chave'],
                    'br_telefone': data.get('telefone', '')[:20],
                    'br_status_pagamento': 'pendente',
                    'br_ip_cliente': request.remote_addr or 'unknown'
                }).execute()

                if response.data:
                    log_info("salvar_ganhador", f"Ganhador salvo: {data['nome']} - {data['valor']}")
                    return jsonify({'sucesso': True, 'id': response.data[0]['br_id']})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao inserir ganhador'})
            except Exception as e:
                log_error("salvar_ganhador", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Verificar duplicata em memória
            for ganhador in memory_storage['ganhadores_rb']:
                if ganhador.get('codigo') == data['codigo']:
                    return jsonify({'sucesso': False, 'erro': 'Código já utilizado'})
            
            ganhador_data['id'] = len(memory_storage['ganhadores_rb']) + 1
            memory_storage['ganhadores_rb'].append(ganhador_data)
            log_info("salvar_ganhador", f"Ganhador salvo em memória: {data['nome']} - {data['valor']}")
            return jsonify({'sucesso': True, 'id': ganhador_data['id']})

    except Exception as e:
        log_error("salvar_ganhador", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS 2 PARA 1000 ==========

@app.route('/enviar_bilhete', methods=['POST'])
def enviar_bilhete():
    """Salva dados do cliente e seus bilhetes do 2 para 1000"""
    try:
        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['nome', 'telefone', 'chave_pix', 'bilhetes']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'sucesso': False, 'erro': f'Campo {campo} é obrigatório'})

        # Validações
        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        if len(data['telefone']) < 10:
            return jsonify({'sucesso': False, 'erro': 'Telefone inválido'})

        if not isinstance(data['bilhetes'], list) or len(data['bilhetes']) == 0:
            return jsonify({'sucesso': False, 'erro': 'Bilhetes inválidos'})

        payment_id = data.get('payment_id') or session.get('payment_id')
        if not payment_id:
            return jsonify({'sucesso': False, 'erro': 'Payment ID não encontrado'})

        cliente_data = {
            'nome': data['nome'].strip()[:255],
            'telefone': data['telefone'].strip()[:20],
            'chave_pix': data['chave_pix'].strip()[:255],
            'bilhetes': data['bilhetes'],
            'payment_id': str(payment_id),
            'data_sorteio': date.today().isoformat(),
            'ip_cliente': request.remote_addr or 'unknown',
            'data_criacao': datetime.now().isoformat()
        }

        if supabase:
            try:
                response = supabase.table('ml_clientes').insert({
                    'ml_nome': data['nome'].strip()[:255],
                    'ml_telefone': data['telefone'].strip()[:20],
                    'ml_chave_pix': data['chave_pix'].strip()[:255],
                    'ml_bilhetes': data['bilhetes'],
                    'ml_payment_id': str(payment_id),
                    'ml_data_sorteio': date.today().isoformat(),
                    'ml_ip_cliente': request.remote_addr or 'unknown'
                }).execute()

                if response.data:
                    log_info("enviar_bilhete", f"Cliente registrado: {data['nome']} - Bilhetes: {data['bilhetes']}")
                    return jsonify({'sucesso': True, 'id': response.data[0]['ml_id']})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao salvar dados'})
            except Exception as e:
                log_error("enviar_bilhete", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            cliente_data['id'] = len(memory_storage['clientes_ml']) + 1
            memory_storage['clientes_ml'].append(cliente_data)
            log_info("enviar_bilhete", f"Cliente registrado em memória: {data['nome']}")
            return jsonify({'sucesso': True, 'id': cliente_data['id']})

    except Exception as e:
        log_error("enviar_bilhete", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/resultado_sorteio')
def resultado_sorteio():
    """Obtém resultado do sorteio do dia do 2 para 1000"""
    try:
        hoje = date.today().isoformat()
        valor_acumulado = obter_premio_acumulado()
        
        if supabase:
            try:
                response = supabase.table('ml_sorteios').select('*').eq('ml_data_sorteio', hoje).execute()

                if response.data:
                    sorteio = response.data[0]
                    log_info("resultado_sorteio", f"Resultado: {sorteio['ml_milhar_sorteada']}")
                    
                    return jsonify({
                        'milhar_sorteada': sorteio['ml_milhar_sorteada'],
                        'houve_ganhador': sorteio['ml_houve_ganhador'],
                        'valor_premio': sorteio.get('ml_valor_premio', ''),
                        'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
                    })
            except Exception as e:
                log_error("resultado_sorteio", e)
        else:
            # Verificar em memória
            for sorteio in memory_storage['sorteios_ml']:
                if sorteio.get('data_sorteio') == hoje:
                    return jsonify({
                        'milhar_sorteada': sorteio['milhar_sorteada'],
                        'houve_ganhador': sorteio['houve_ganhador'],
                        'valor_premio': sorteio.get('valor_premio', ''),
                        'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
                    })
        
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
        })

    except Exception as e:
        log_error("resultado_sorteio", e)
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{PREMIO_INICIAL_ML:.2f}".replace('.', ',')
        })

@app.route('/ultimos_ganhadores')
def ultimos_ganhadores():
    """Obtém últimos ganhadores do 2 para 1000"""
    try:
        ganhadores = []
        
        if supabase:
            try:
                response = supabase.table('ml_ganhadores').select(
                    'ml_nome, ml_valor, ml_milhar_sorteada, ml_bilhete_premiado, ml_data_sorteio'
                ).order('ml_data_sorteio', desc=True).limit(10).execute()

                for ganhador in (response.data or []):
                    nome_display = ganhador['ml_nome']
                    if len(nome_display) > 15:
                        nome_display = nome_display[:15] + '...'
                    
                    ganhadores.append({
                        'nome': nome_display,
                        'valor': ganhador['ml_valor'],
                        'milhar': ganhador['ml_milhar_sorteada'],
                        'data': datetime.fromisoformat(ganhador['ml_data_sorteio']).strftime('%d/%m/%Y')
                    })
            except Exception as e:
                log_error("ultimos_ganhadores", e)
        else:
            # Buscar em memória
            ganhadores_ordenados = sorted(
                memory_storage['ganhadores_ml'], 
                key=lambda x: x.get('data_sorteio', ''), 
                reverse=True
            )[:10]
            
            for ganhador in ganhadores_ordenados:
                nome_display = ganhador['nome']
                if len(nome_display) > 15:
                    nome_display = nome_display[:15] + '...'
                
                ganhadores.append({
                    'nome': nome_display,
                    'valor': ganhador['valor'],
                    'milhar': ganhador['milhar_sorteada'],
                    'data': datetime.fromisoformat(ganhador['data_sorteio']).strftime('%d/%m/%Y')
                })

        log_info("ultimos_ganhadores", f"Últimos ganhadores ML: {len(ganhadores)} encontrados")
        return jsonify({'ganhadores': ganhadores})

    except Exception as e:
        log_error("ultimos_ganhadores", e)
        return jsonify({'ganhadores': []})

# ========== ROTAS DE AFILIADOS ==========

@app.route('/cadastrar_afiliado', methods=['POST'])
def cadastrar_afiliado():
    """Cadastra novo afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['nome', 'email', 'telefone', 'cpf']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'sucesso': False, 'erro': f'Campo {campo} é obrigatório'})

        # Validações
        cpf = data['cpf'].replace('.', '').replace('-', '').replace(' ', '')
        if len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})

        if '@' not in data['email'] or len(data['email']) < 5:
            return jsonify({'sucesso': False, 'erro': 'E-mail inválido'})

        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        codigo = gerar_codigo_afiliado()

        afiliado_data = {
            'codigo': codigo,
            'nome': data['nome'].strip()[:255],
            'email': data['email'].strip().lower()[:255],
            'telefone': data['telefone'].strip()[:20],
            'cpf': cpf,
            'status': 'ativo',
            'total_clicks': 0,
            'total_vendas': 0,
            'total_comissao': 0,
            'saldo_disponivel': 0,
            'ip_cadastro': request.remote_addr or 'unknown',
            'data_criacao': datetime.now().isoformat()
        }

        if supabase:
            try:
                # Verificar duplicatas
                existing_email = supabase.table('br_afiliados').select('br_id').eq('br_email', data['email']).execute()
                existing_cpf = supabase.table('br_afiliados').select('br_id').eq('br_cpf', cpf).execute()
                
                if existing_email.data:
                    return jsonify({'sucesso': False, 'erro': 'E-mail já cadastrado'})
                
                if existing_cpf.data:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})

                response = supabase.table('br_afiliados').insert({
                    'br_codigo': codigo,
                    'br_nome': data['nome'].strip()[:255],
                    'br_email': data['email'].strip().lower()[:255],
                    'br_telefone': data['telefone'].strip()[:20],
                    'br_cpf': cpf,
                    'br_status': 'ativo',
                    'br_total_clicks': 0,
                    'br_total_vendas': 0,
                    'br_total_comissao': 0,
                    'br_saldo_disponivel': 0,
                    'br_ip_cadastro': request.remote_addr or 'unknown'
                }).execute()

                if response.data:
                    afiliado = response.data[0]
                    log_info("cadastrar_afiliado", f"Novo afiliado cadastrado: {data['nome']} - {codigo}")
                    
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['br_id'],
                            'codigo': codigo,
                            'nome': afiliado['br_nome'],
                            'email': afiliado['br_email'],
                            'total_clicks': 0,
                            'total_vendas': 0,
                            'total_comissao': 0,
                            'saldo_disponivel': 0,
                            'link': f"{request.url_root}?ref={codigo}"
                        }
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao inserir afiliado'})
            except Exception as e:
                log_error("cadastrar_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Verificar duplicatas em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('email') == data['email'] or afiliado.get('cpf') == cpf:
                    return jsonify({'sucesso': False, 'erro': 'E-mail ou CPF já cadastrado'})
            
            afiliado_data['id'] = len(memory_storage['afiliados']) + 1
            memory_storage['afiliados'].append(afiliado_data)
            log_info("cadastrar_afiliado", f"Afiliado cadastrado em memória: {data['nome']} - {codigo}")
            
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'id': afiliado_data['id'],
                    'codigo': codigo,
                    'nome': afiliado_data['nome'],
                    'email': afiliado_data['email'],
                    'total_clicks': 0,
                    'total_vendas': 0,
                    'total_comissao': 0,
                    'saldo_disponivel': 0,
                    'link': f"{request.url_root}?ref={codigo}"
                }
            })

    except Exception as e:
        log_error("cadastrar_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/login_afiliado', methods=['POST'])
def login_afiliado():
    """Login do afiliado por CPF"""
    try:
        data = sanitizar_dados_entrada(request.json)
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})

        if supabase:
            try:
                response = supabase.table('br_afiliados').select('*').eq('br_cpf', cpf).eq('br_status', 'ativo').execute()
                
                if response.data:
                    afiliado = response.data[0]
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['br_id'],
                            'codigo': afiliado['br_codigo'],
                            'nome': afiliado['br_nome'],
                            'email': afiliado['br_email'],
                            'total_clicks': afiliado['br_total_clicks'] or 0,
                            'total_vendas': afiliado['br_total_vendas'] or 0,
                            'total_comissao': float(afiliado['br_total_comissao'] or 0),
                            'saldo_disponivel': float(afiliado['br_saldo_disponivel'] or 0),
                            'chave_pix': afiliado.get('br_chave_pix'),
                            'tipo_chave_pix': afiliado.get('br_tipo_chave_pix')
                        }
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'CPF não encontrado ou afiliado inativo'})
            except Exception as e:
                log_error("login_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Buscar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('cpf') == cpf and afiliado.get('status') == 'ativo':
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['id'],
                            'codigo': afiliado['codigo'],
                            'nome': afiliado['nome'],
                            'email': afiliado['email'],
                            'total_clicks': afiliado['total_clicks'],
                            'total_vendas': afiliado['total_vendas'],
                            'total_comissao': afiliado['total_comissao'],
                            'saldo_disponivel': afiliado['saldo_disponivel'],
                            'chave_pix': afiliado.get('chave_pix'),
                            'tipo_chave_pix': afiliado.get('tipo_chave_pix')
                        }
                    })
            
            return jsonify({'sucesso': False, 'erro': 'CPF não encontrado ou afiliado inativo'})

    except Exception as e:
        log_error("login_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/atualizar_pix_afiliado', methods=['POST'])
def atualizar_pix_afiliado():
    """Atualiza chave PIX do afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')

        if not codigo or not chave_pix:
            return jsonify({'sucesso': False, 'erro': 'Código e chave PIX são obrigatórios'})

        if len(chave_pix) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})

        if supabase:
            try:
                response = supabase.table('br_afiliados').update({
                    'br_chave_pix': chave_pix,
                    'br_tipo_chave_pix': tipo_chave
                }).eq('br_codigo', codigo).eq('br_status', 'ativo').execute()

                if response.data:
                    log_info("atualizar_pix_afiliado", f"PIX atualizado para afiliado {codigo}")
                    return jsonify({'sucesso': True})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
            except Exception as e:
                log_error("atualizar_pix_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Atualizar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('codigo') == codigo and afiliado.get('status') == 'ativo':
                    afiliado['chave_pix'] = chave_pix
                    afiliado['tipo_chave_pix'] = tipo_chave
                    log_info("atualizar_pix_afiliado", f"PIX atualizado em memória para afiliado {codigo}")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

    except Exception as e:
        log_error("atualizar_pix_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/solicitar_saque_afiliado', methods=['POST'])
def solicitar_saque_afiliado():
    """Processa solicitação de saque do afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código do afiliado é obrigatório'})

        saque_minimo = 10.00

        if supabase:
            try:
                afiliado_response = supabase.table('br_afiliados').select('*').eq('br_codigo', codigo).eq('br_status', 'ativo').execute()

                if not afiliado_response.data:
                    return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

                afiliado = afiliado_response.data[0]
                saldo = float(afiliado['br_saldo_disponivel'] or 0)

                if saldo < saque_minimo:
                    return jsonify({'sucesso': False, 'erro': f'Saldo insuficiente. Mínimo: R$ {saque_minimo:.2f}'})

                if not afiliado['br_chave_pix']:
                    return jsonify({'sucesso': False, 'erro': 'Configure sua chave PIX primeiro'})

                # Verificar se não há saque pendente
                saque_pendente = supabase.table('br_saques_afiliados').select('br_id').eq(
                    'br_afiliado_id', afiliado['br_id']
                ).eq('br_status', 'solicitado').execute()

                if saque_pendente.data:
                    return jsonify({'sucesso': False, 'erro': 'Você já possui um saque pendente'})

                saque_response = supabase.table('br_saques_afiliados').insert({
                    'br_afiliado_id': afiliado['br_id'],
                    'br_valor': saldo,
                    'br_chave_pix': afiliado['br_chave_pix'],
                    'br_tipo_chave': afiliado['br_tipo_chave_pix'],
                    'br_status': 'solicitado',
                    'br_data_solicitacao': datetime.now().isoformat(),
                    'br_ip_solicitacao': request.remote_addr or 'unknown'
                }).execute()

                if saque_response.data:
                    # Zerar saldo do afiliado
                    supabase.table('br_afiliados').update({
                        'br_saldo_disponivel': 0
                    }).eq('br_id', afiliado['br_id']).execute()

                    log_info("solicitar_saque_afiliado", f"Saque solicitado: {afiliado['br_nome']} - R$ {saldo:.2f}")

                    return jsonify({
                        'sucesso': True,
                        'valor': saldo,
                        'saque_id': saque_response.data[0]['br_id']
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao processar saque'})
            except Exception as e:
                log_error("solicitar_saque_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Processar em memória
            afiliado_encontrado = None
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('codigo') == codigo and afiliado.get('status') == 'ativo':
                    afiliado_encontrado = afiliado
                    break
            
            if not afiliado_encontrado:
                return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

            saldo = float(afiliado_encontrado.get('saldo_disponivel', 0))

            if saldo < saque_minimo:
                return jsonify({'sucesso': False, 'erro': f'Saldo insuficiente. Mínimo: R$ {saque_minimo:.2f}'})

            if not afiliado_encontrado.get('chave_pix'):
                return jsonify({'sucesso': False, 'erro': 'Configure sua chave PIX primeiro'})

            # Verificar se não há saque pendente
            for saque in memory_storage['saques']:
                if saque.get('afiliado_id') == afiliado_encontrado['id'] and saque.get('status') == 'solicitado':
                    return jsonify({'sucesso': False, 'erro': 'Você já possui um saque pendente'})

            # Criar saque
            saque_data = {
                'id': len(memory_storage['saques']) + 1,
                'afiliado_id': afiliado_encontrado['id'],
                'valor': saldo,
                'chave_pix': afiliado_encontrado['chave_pix'],
                'tipo_chave': afiliado_encontrado.get('tipo_chave_pix', 'cpf'),
                'status': 'solicitado',
                'data_solicitacao': datetime.now().isoformat(),
                'ip_solicitacao': request.remote_addr or 'unknown'
            }

            memory_storage['saques'].append(saque_data)

            # Zerar saldo do afiliado
            afiliado_encontrado['saldo_disponivel'] = 0

            log_info("solicitar_saque_afiliado", f"Saque solicitado em memória: {afiliado_encontrado['nome']} - R$ {saldo:.2f}")

            return jsonify({
                'sucesso': True,
                'valor': saldo,
                'saque_id': saque_data['id']
            })

    except Exception as e:
        log_error("solicitar_saque_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/registrar_clique_afiliado', methods=['POST'])
def registrar_clique_afiliado():
    """Registra clique no link do afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código é obrigatório'})

        if supabase:
            try:
                # Buscar afiliado
                afiliado_response = supabase.table('br_afiliados').select('*').eq('br_codigo', codigo).eq('br_status', 'ativo').execute()
                
                if afiliado_response.data:
                    afiliado = afiliado_response.data[0]
                    
                    # Registrar click
                    supabase.table('br_afiliado_clicks').insert({
                        'br_afiliado_id': afiliado['br_id'],
                        'br_ip_visitor': request.remote_addr or 'unknown',
                        'br_user_agent': request.headers.get('User-Agent', '')[:500],
                        'br_referrer': request.headers.get('Referer', '')[:500]
                    }).execute()
                    
                    # Atualizar contador do afiliado
                    novo_total = (afiliado['br_total_clicks'] or 0) + 1
                    supabase.table('br_afiliados').update({
                        'br_total_clicks': novo_total
                    }).eq('br_id', afiliado['br_id']).execute()
                    
                    log_info("registrar_clique_afiliado", f"Click registrado para afiliado {codigo}, total: {novo_total}")
                    return jsonify({'sucesso': True})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
            except Exception as e:
                log_error("registrar_clique_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Processar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('codigo') == codigo and afiliado.get('status') == 'ativo':
                    afiliado['total_clicks'] = afiliado.get('total_clicks', 0) + 1
                    log_info("registrar_clique_afiliado", f"Click registrado em memória para afiliado {codigo}")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

    except Exception as e:
        log_error("registrar_clique_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS ADMIN ==========

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login do admin"""
    try:
        data = sanitizar_dados_entrada(request.json)
        senha = data.get('senha')
        
        if not senha:
            return jsonify({'success': False, 'message': 'Senha é obrigatória'})
        
        if senha == ADMIN_PASSWORD:
            session['admin_logado'] = True
            session['admin_login_time'] = datetime.now().isoformat()
            log_info("admin_login", "Admin logado com sucesso")
            return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
        
        log_error("admin_login", "Tentativa de login com senha incorreta", {"ip": request.remote_addr})
        return jsonify({'success': False, 'message': 'Senha incorreta'})
    
    except Exception as e:
        log_error("admin_login", e)
        return jsonify({'success': False, 'message': 'Erro interno do servidor'})

@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema unificado"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403

        game = request.args.get('game', 'both')
        
        stats = {
            'vendidas': 0,
            'bilhetes_vendidos': 0,
            'ganhadores': 0,
            'total_ganhadores': 0,
            'afiliados': 0,
            'vendas_hoje': 0,
            'vendas_hoje_ml': 0,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS,
            'premios_restantes': 0,
            'premio_atual': f"{obter_premio_acumulado():.2f}".replace('.', ','),
            'sistema_ativo': obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        }
        
        if game in ['raspa_brasil', 'both']:
            vendidas_rb = obter_total_vendas('raspa_brasil')
            stats['vendidas'] = vendidas_rb
            stats['restantes'] = TOTAL_RASPADINHAS - vendidas_rb
            
            if supabase:
                try:
                    ganhadores_rb = supabase.table('br_ganhadores').select('br_id').execute()
                    stats['ganhadores'] = len(ganhadores_rb.data or [])
                    
                    afiliados = supabase.table('br_afiliados').select('br_id').eq('br_status', 'ativo').execute()
                    stats['afiliados'] = len(afiliados.data or [])
                except:
                    pass
            else:
                stats['ganhadores'] = len(memory_storage['ganhadores_rb'])
                stats['afiliados'] = len([a for a in memory_storage['afiliados'] if a.get('status') == 'ativo'])
        
        if game in ['2para1000', 'both']:
            vendidos_ml = obter_total_vendas('2para1000')
            stats['bilhetes_vendidos'] = vendidos_ml
            
            if supabase:
                try:
                    ganhadores_ml = supabase.table('ml_ganhadores').select('ml_id').execute()
                    stats['total_ganhadores'] = len(ganhadores_ml.data or [])
                except:
                    pass
            else:
                stats['total_ganhadores'] = len(memory_storage['ganhadores_ml'])

        log_info("admin_stats", f"Stats consultadas - Game: {game}")
        return jsonify(stats)

    except Exception as e:
        log_error("admin_stats", e)
        return jsonify(stats)

@app.route('/admin/liberar_premio_manual', methods=['POST'])
def admin_liberar_premio_manual():
    """Libera prêmio manual para próxima raspagem"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        valor = data.get('valor')
        
        if not valor:
            return jsonify({'sucesso': False, 'erro': 'Valor é obrigatório'})
        
        valor = valor.strip()
        if not valor.startswith('R$'):
            return jsonify({'sucesso': False, 'erro': 'Formato inválido. Use: R$ 00,00'})
        
        # Verificar se não há prêmio já liberado
        premio_existente = obter_configuracao('premio_manual_liberado', '')
        if premio_existente:
            return jsonify({'sucesso': False, 'erro': 'Já existe um prêmio liberado aguardando'})
        
        if atualizar_configuracao('premio_manual_liberado', valor, 'raspa_brasil'):
            log_info("admin_liberar_premio_manual", f"Prêmio manual liberado: {valor}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar configuração'})
        
    except Exception as e:
        log_error("admin_liberar_premio_manual", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/verificar_status_premio')
def admin_verificar_status_premio():
    """Verifica se há prêmio liberado aguardando"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        premio_liberado = obter_configuracao('premio_manual_liberado', '')
        
        return jsonify({
            'premio_liberado': bool(premio_liberado),
            'valor': premio_liberado if premio_liberado else None
        })
    except Exception as e:
        log_error("admin_verificar_status_premio", e)
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/admin/sortear', methods=['POST'])
def admin_sortear():
    """Realiza sorteio diário do 2 para 1000"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403

        data = sanitizar_dados_entrada(request.json)
        milhar_sorteada = data.get('milhar_sorteada', '').strip()

        if not milhar_sorteada or len(milhar_sorteada) != 4 or not milhar_sorteada.isdigit():
            return jsonify({'sucesso': False, 'erro': 'Milhar deve ter exatamente 4 dígitos'})

        hoje = date.today().isoformat()

        # Verificar se já foi sorteado hoje
        sorteio_existente = False
        if supabase:
            try:
                existing = supabase.table('ml_sorteios').select('ml_id').eq('ml_data_sorteio', hoje).execute()
                if existing.data:
                    sorteio_existente = True
            except:
                pass
        else:
            for sorteio in memory_storage['sorteios_ml']:
                if sorteio.get('data_sorteio') == hoje:
                    sorteio_existente = True
                    break

        if sorteio_existente:
            return jsonify({'sucesso': False, 'erro': 'Sorteio já foi realizado hoje'})

        # Buscar clientes participantes
        clientes_participantes = []
        if supabase:
            try:
                clientes_response = supabase.table('ml_clientes').select('*').eq('ml_data_sorteio', hoje).execute()
                clientes_participantes = clientes_response.data or []
            except:
                pass
        else:
            for cliente in memory_storage['clientes_ml']:
                if cliente.get('data_sorteio') == hoje:
                    clientes_participantes.append(cliente)

        houve_ganhador = False
        ganhador_data = None
        valor_premio = obter_premio_acumulado()

        # Verificar se algum bilhete ganhou
        for cliente in clientes_participantes:
            bilhetes = cliente.get('bilhetes', cliente.get('ml_bilhetes', []))
            if milhar_sorteada in bilhetes:
                houve_ganhador = True
                ganhador_data = cliente
                log_info("admin_sortear", f"GANHADOR ENCONTRADO: {cliente.get('nome', cliente.get('ml_nome'))} - Bilhete: {milhar_sorteada}")
                break

        if houve_ganhador:
            # Salvar ganhador
            ganhador_info = {
                'nome': ganhador_data.get('nome', ganhador_data.get('ml_nome')),
                'telefone': ganhador_data.get('telefone', ganhador_data.get('ml_telefone')),
                'chave_pix': ganhador_data.get('chave_pix', ganhador_data.get('ml_chave_pix')),
                'bilhete_premiado': milhar_sorteada,
                'milhar_sorteada': milhar_sorteada,
                'valor': f"R$ {valor_premio:.2f}".replace('.', ','),
                'data_sorteio': hoje,
                'status_pagamento': 'pendente',
                'ip_cliente': ganhador_data.get('ip_cliente', ganhador_data.get('ml_ip_cliente', 'unknown'))
            }

            if supabase:
                try:
                    supabase.table('ml_ganhadores').insert({
                        'ml_nome': ganhador_info['nome'],
                        'ml_telefone': ganhador_info['telefone'],
                        'ml_chave_pix': ganhador_info['chave_pix'],
                        'ml_bilhete_premiado': milhar_sorteada,
                        'ml_milhar_sorteada': milhar_sorteada,
                        'ml_valor': ganhador_info['valor'],
                        'ml_data_sorteio': hoje,
                        'ml_status_pagamento': 'pendente',
                        'ml_ip_cliente': ganhador_info['ip_cliente']
                    }).execute()
                except Exception as e:
                    log_error("admin_sortear", e)
            else:
                ganhador_info['id'] = len(memory_storage['ganhadores_ml']) + 1
                memory_storage['ganhadores_ml'].append(ganhador_info)

            # Resetar prêmio
            atualizar_configuracao('premio_acumulado', str(PREMIO_INICIAL_ML), '2para1000')
            novo_valor_acumulado = PREMIO_INICIAL_ML

            log_info("admin_sortear", f"GANHADOR! {ganhador_info['nome']} - Bilhete: {milhar_sorteada} - Prêmio: R$ {valor_premio:.2f}")

        else:
            # Acumular prêmio
            novo_valor_acumulado = valor_premio + PREMIO_INICIAL_ML
            atualizar_configuracao('premio_acumulado', str(novo_valor_acumulado), '2para1000')

            log_info("admin_sortear", f"Prêmio acumulado! Novo valor: R$ {novo_valor_acumulado:.2f}")

        # Salvar resultado do sorteio
        sorteio_data = {
            'data_sorteio': hoje,
            'milhar_sorteada': milhar_sorteada,
            'houve_ganhador': houve_ganhador,
            'valor_premio': f"R$ {valor_premio:.2f}".replace('.', ',') if houve_ganhador else '',
            'novo_valor_acumulado': f"R$ {novo_valor_acumulado:.2f}".replace('.', ','),
            'admin_responsavel': session.get('admin_login_time', 'unknown')
        }

        if supabase:
            try:
                supabase.table('ml_sorteios').insert({
                    'ml_data_sorteio': hoje,
                    'ml_milhar_sorteada': milhar_sorteada,
                    'ml_houve_ganhador': houve_ganhador,
                    'ml_valor_premio': sorteio_data['valor_premio'],
                    'ml_novo_valor_acumulado': sorteio_data['novo_valor_acumulado'],
                    'ml_admin_responsavel': sorteio_data['admin_responsavel']
                }).execute()
            except Exception as e:
                log_error("admin_sortear", e)
        else:
            sorteio_data['id'] = len(memory_storage['sorteios_ml']) + 1
            memory_storage['sorteios_ml'].append(sorteio_data)

        return jsonify({
            'sucesso': True,
            'houve_ganhador': houve_ganhador,
            'ganhador': {
                'nome': ganhador_data.get('nome', ganhador_data.get('ml_nome', '')) if ganhador_data else '',
                'bilhete': milhar_sorteada
            } if houve_ganhador else None,
            'valor_premio': f"{valor_premio:.2f}".replace('.', ','),
            'novo_valor_acumulado': f"{novo_valor_acumulado:.2f}".replace('.', ',')
        })

    except Exception as e:
        log_error("admin_sortear", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== OUTRAS ROTAS ADMIN ==========

@app.route('/admin/ganhadores/<game>')
def admin_ganhadores(game):
    """Obtém lista de ganhadores para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data_filtro = request.args.get('data')
        ganhadores = []
        
        if supabase:
            try:
                if game in ['raspa_brasil', 'todos']:
                    query = supabase.table('br_ganhadores').select('*').order('br_data_criacao', desc=True)
                    if data_filtro:
                        query = query.gte('br_data_criacao', data_filtro + ' 00:00:00').lt('br_data_criacao', data_filtro + ' 23:59:59')
                    
                    rb_response = query.limit(20).execute()
                    for g in (rb_response.data or []):
                        ganhadores.append({
                            'id': g['br_id'],
                            'nome': g['br_nome'],
                            'valor': g['br_valor'],
                            'codigo': g['br_codigo'],
                            'data': g['br_data_criacao'],
                            'status': g['br_status_pagamento'],
                            'jogo': 'Raspa Brasil',
                            'chave_pix': g.get('br_chave_pix', '')
                        })
                
                if game in ['2para1000', 'todos']:
                    query = supabase.table('ml_ganhadores').select('*').order('ml_data_sorteio', desc=True)
                    if data_filtro:
                        query = query.eq('ml_data_sorteio', data_filtro)
                    
                    ml_response = query.limit(20).execute()
                    for g in (ml_response.data or []):
                        ganhadores.append({
                            'id': g['ml_id'],
                            'nome': g['ml_nome'],
                            'valor': g['ml_valor'],
                            'milhar': g['ml_bilhete_premiado'],
                            'data': g['ml_data_sorteio'],
                            'status': g['ml_status_pagamento'],
                            'jogo': '2 para 1000',
                            'chave_pix': g.get('ml_chave_pix', '')
                        })
            except Exception as e:
                log_error("admin_ganhadores", e)
        else:
            # Buscar em memória
            if game in ['raspa_brasil', 'todos']:
                for g in memory_storage['ganhadores_rb']:
                    if not data_filtro or g.get('data_criacao', '')[:10] == data_filtro:
                        ganhadores.append({
                            'id': g['id'],
                            'nome': g['nome'],
                            'valor': g['valor'],
                            'codigo': g['codigo'],
                            'data': g['data_criacao'],
                            'status': g['status_pagamento'],
                            'jogo': 'Raspa Brasil',
                            'chave_pix': g.get('chave_pix', '')
                        })
            
            if game in ['2para1000', 'todos']:
                for g in memory_storage['ganhadores_ml']:
                    if not data_filtro or g.get('data_sorteio') == data_filtro:
                        ganhadores.append({
                            'id': g['id'],
                            'nome': g['nome'],
                            'valor': g['valor'],
                            'milhar': g['bilhete_premiado'],
                            'data': g['data_sorteio'],
                            'status': g['status_pagamento'],
                            'jogo': '2 para 1000',
                            'chave_pix': g.get('chave_pix', '')
                        })
        
        # Ordenar por data
        ganhadores.sort(key=lambda x: x['data'], reverse=True)
        
        log_info("admin_ganhadores", f"Ganhadores consultados - Game: {game}, Total: {len(ganhadores[:20])}")
        return jsonify({'ganhadores': ganhadores[:20]})
        
    except Exception as e:
        log_error("admin_ganhadores", e)
        return jsonify({'ganhadores': []})

@app.route('/admin/adicionar_ganhador', methods=['POST'])
def admin_adicionar_ganhador():
    """Adiciona ganhador manual"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        jogo = data.get('jogo')
        nome = data.get('nome', '').strip()
        valor = data.get('valor', '').strip()
        chave_pix = data.get('chave_pix', '').strip()
        
        if not all([jogo, nome, valor, chave_pix]):
            return jsonify({'sucesso': False, 'erro': 'Todos os campos são obrigatórios'})
        
        # Validações
        if len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if len(chave_pix) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})
        
        if jogo == 'raspa_brasil':
            codigo = gerar_codigo_antifraude()
            ganhador_data = {
                'codigo': codigo,
                'nome': nome,
                'valor': valor,
                'chave_pix': chave_pix,
                'tipo_chave': 'cpf',
                'status_pagamento': 'pendente',
                'ip_cliente': request.remote_addr or 'unknown',
                'admin_manual': True,
                'data_criacao': datetime.now().isoformat()
            }
            
            if supabase:
                try:
                    response = supabase.table('br_ganhadores').insert({
                        'br_codigo': codigo,
                        'br_nome': nome,
                        'br_valor': valor,
                        'br_chave_pix': chave_pix,
                        'br_tipo_chave': 'cpf',
                        'br_status_pagamento': 'pendente',
                        'br_ip_cliente': request.remote_addr or 'unknown',
                        'br_admin_manual': True
                    }).execute()
                    
                    if response.data:
                        log_info("admin_adicionar_ganhador", f"Ganhador RB manual adicionado: {nome} - {valor}")
                        return jsonify({'sucesso': True})
                except Exception as e:
                    log_error("admin_adicionar_ganhador", e)
                    return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
            else:
                ganhador_data['id'] = len(memory_storage['ganhadores_rb']) + 1
                memory_storage['ganhadores_rb'].append(ganhador_data)
                log_info("admin_adicionar_ganhador", f"Ganhador RB manual adicionado em memória: {nome} - {valor}")
                return jsonify({'sucesso': True})
            
        elif jogo == '2para1000':
            bilhete = data.get('bilhete_premiado', '').strip()
            if not bilhete or len(bilhete) != 4 or not bilhete.isdigit():
                return jsonify({'sucesso': False, 'erro': 'Bilhete deve ter 4 dígitos'})
            
            ganhador_data = {
                'nome': nome,
                'valor': valor,
                'chave_pix': chave_pix,
                'bilhete_premiado': bilhete,
                'milhar_sorteada': bilhete,
                'data_sorteio': date.today().isoformat(),
                'status_pagamento': 'pendente',
                'ip_cliente': request.remote_addr or 'unknown',
                'admin_manual': True
            }
            
            if supabase:
                try:
                    response = supabase.table('ml_ganhadores').insert({
                        'ml_nome': nome,
                        'ml_valor': valor,
                        'ml_chave_pix': chave_pix,
                        'ml_bilhete_premiado': bilhete,
                        'ml_milhar_sorteada': bilhete,
                        'ml_data_sorteio': date.today().isoformat(),
                        'ml_status_pagamento': 'pendente',
                        'ml_ip_cliente': request.remote_addr or 'unknown',
                        'ml_admin_manual': True
                    }).execute()
                    
                    if response.data:
                        log_info("admin_adicionar_ganhador", f"Ganhador ML manual adicionado: {nome} - {valor}")
                        return jsonify({'sucesso': True})
                except Exception as e:
                    log_error("admin_adicionar_ganhador", e)
                    return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
            else:
                ganhador_data['id'] = len(memory_storage['ganhadores_ml']) + 1
                memory_storage['ganhadores_ml'].append(ganhador_data)
                log_info("admin_adicionar_ganhador", f"Ganhador ML manual adicionado em memória: {nome} - {valor}")
                return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Jogo inválido'})
        
        return jsonify({'sucesso': False, 'erro': 'Erro ao inserir ganhador'})
            
    except Exception as e:
        log_error("admin_adicionar_ganhador", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/alterar_status_ganhador', methods=['POST'])
def admin_alterar_status_ganhador():
    """Altera status do ganhador"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        ganhador_id = data.get('id')
        jogo = data.get('jogo')
        status = data.get('status')
        
        if not all([ganhador_id, jogo, status]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if status not in ['pendente', 'pago']:
            return jsonify({'sucesso': False, 'erro': 'Status inválido'})
        
        update_data = {
            'status_pagamento': status,
            'data_pagamento': datetime.now().isoformat() if status == 'pago' else None
        }

        if supabase:
            try:
                if jogo == 'Raspa Brasil':
                    response = supabase.table('br_ganhadores').update({
                        'br_status_pagamento': status,
                        'br_data_pagamento': datetime.now().isoformat() if status == 'pago' else None
                    }).eq('br_id', ganhador_id).execute()
                elif jogo == '2 para 1000':
                    response = supabase.table('ml_ganhadores').update({
                        'ml_status_pagamento': status,
                        'ml_data_pagamento': datetime.now().isoformat() if status == 'pago' else None
                    }).eq('ml_id', ganhador_id).execute()
                else:
                    return jsonify({'sucesso': False, 'erro': 'Jogo inválido'})
                
                if response.data:
                    log_info("admin_alterar_status_ganhador", f"Status alterado: Ganhador {ganhador_id} - {jogo} -> {status}")
                    return jsonify({'sucesso': True})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Ganhador não encontrado'})
            except Exception as e:
                log_error("admin_alterar_status_ganhador", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Atualizar em memória
            ganhadores_key = 'ganhadores_rb' if jogo == 'Raspa Brasil' else 'ganhadores_ml'
            for ganhador in memory_storage[ganhadores_key]:
                if ganhador.get('id') == int(ganhador_id):
                    ganhador.update(update_data)
                    log_info("admin_alterar_status_ganhador", f"Status alterado em memória: Ganhador {ganhador_id} - {jogo} -> {status}")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Ganhador não encontrado'})
            
    except Exception as e:
        log_error("admin_alterar_status_ganhador", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/remover_ganhador', methods=['POST'])
def admin_remover_ganhador():
    """Remove ganhador"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        ganhador_id = data.get('id')
        jogo = data.get('jogo')
        
        if not all([ganhador_id, jogo]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if supabase:
            try:
                if jogo == 'Raspa Brasil':
                    response = supabase.table('br_ganhadores').delete().eq('br_id', ganhador_id).execute()
                elif jogo == '2 para 1000':
                    response = supabase.table('ml_ganhadores').delete().eq('ml_id', ganhador_id).execute()
                else:
                    return jsonify({'sucesso': False, 'erro': 'Jogo inválido'})
                
                log_info("admin_remover_ganhador", f"Ganhador removido: ID {ganhador_id} - {jogo}")
                return jsonify({'sucesso': True})
            except Exception as e:
                log_error("admin_remover_ganhador", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Remover da memória
            ganhadores_key = 'ganhadores_rb' if jogo == 'Raspa Brasil' else 'ganhadores_ml'
            memory_storage[ganhadores_key] = [
                g for g in memory_storage[ganhadores_key] 
                if g.get('id') != int(ganhador_id)
            ]
            log_info("admin_remover_ganhador", f"Ganhador removido da memória: ID {ganhador_id} - {jogo}")
            return jsonify({'sucesso': True})
            
    except Exception as e:
        log_error("admin_remover_ganhador", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/afiliados')
def admin_afiliados():
    """Obtém dados dos afiliados para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        afiliados = []
        
        if supabase:
            try:
                response = supabase.table('br_afiliados').select('*').eq('br_status', 'ativo').order('br_total_comissao', desc=True).limit(100).execute()
                
                for a in (response.data or []):
                    afiliados.append({
                        'nome': a['br_nome'],
                        'codigo': a['br_codigo'],
                        'email': a['br_email'],
                        'total_clicks': a['br_total_clicks'] or 0,
                        'total_vendas': a['br_total_vendas'] or 0,
                        'total_comissao': float(a['br_total_comissao'] or 0),
                        'saldo_disponivel': float(a['br_saldo_disponivel'] or 0),
                        'data_cadastro': a['br_data_criacao']
                    })
            except Exception as e:
                log_error("admin_afiliados", e)
        else:
            for a in memory_storage['afiliados']:
                if a.get('status') == 'ativo':
                    afiliados.append({
                        'nome': a['nome'],
                        'codigo': a['codigo'],
                        'email': a['email'],
                        'total_clicks': a['total_clicks'],
                        'total_vendas': a['total_vendas'],
                        'total_comissao': a['total_comissao'],
                        'saldo_disponivel': a['saldo_disponivel'],
                        'data_cadastro': a['data_criacao']
                    })
        
        log_info("admin_afiliados", f"Afiliados consultados: {len(afiliados)}")
        return jsonify({'afiliados': afiliados})
        
    except Exception as e:
        log_error("admin_afiliados", e)
        return jsonify({'afiliados': []})

@app.route('/admin/saques/<status>')
def admin_saques(status):
    """Obtém lista de saques para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        saques = []
        
        if supabase:
            try:
                query = supabase.table('br_saques_afiliados').select('''
                    br_id, br_valor, br_chave_pix, br_tipo_chave, br_status, br_data_solicitacao,
                    br_afiliados (br_nome, br_codigo)
                ''')
                
                if status == 'pendente':
                    query = query.eq('br_status', 'solicitado')
                elif status == 'pago':
                    query = query.eq('br_status', 'pago')
                
                response = query.order('br_data_solicitacao', desc=True).limit(100).execute()
                
                for s in (response.data or []):
                    afiliado = s.get('br_afiliados', {})
                    saques.append({
                        'id': s['br_id'],
                        'valor': s['br_valor'],
                        'chave_pix': s['br_chave_pix'],
                        'tipo_chave': s['br_tipo_chave'],
                        'status': s['br_status'],
                        'data_solicitacao': s['br_data_solicitacao'],
                        'afiliado_nome': afiliado.get('br_nome', 'N/A'),
                        'afiliado_codigo': afiliado.get('br_codigo', 'N/A')
                    })
            except Exception as e:
                log_error("admin_saques", e)
        else:
            for s in memory_storage['saques']:
                if status == 'todos' or s.get('status') == status or (status == 'pendente' and s.get('status') == 'solicitado'):
                    # Buscar dados do afiliado
                    afiliado_nome = 'N/A'
                    afiliado_codigo = 'N/A'
                    for a in memory_storage['afiliados']:
                        if a.get('id') == s.get('afiliado_id'):
                            afiliado_nome = a['nome']
                            afiliado_codigo = a['codigo']
                            break
                    
                    saques.append({
                        'id': s['id'],
                        'valor': s['valor'],
                        'chave_pix': s['chave_pix'],
                        'tipo_chave': s['tipo_chave'],
                        'status': s['status'],
                        'data_solicitacao': s['data_solicitacao'],
                        'afiliado_nome': afiliado_nome,
                        'afiliado_codigo': afiliado_codigo
                    })
        
        log_info("admin_saques", f"Saques consultados - Status: {status}, Total: {len(saques)}")
        return jsonify({'saques': saques})
        
    except Exception as e:
        log_error("admin_saques", e)
        return jsonify({'saques': []})

@app.route('/admin/marcar_saque_pago', methods=['POST'])
def admin_marcar_saque_pago():
    """Marca saque como pago"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        saque_id = data.get('saque_id')
        
        if not saque_id:
            return jsonify({'sucesso': False, 'erro': 'ID do saque é obrigatório'})
        
        if supabase:
            try:
                response = supabase.table('br_saques_afiliados').update({
                    'br_status': 'pago',
                    'br_data_pagamento': datetime.now().isoformat(),
                    'br_admin_responsavel': session.get('admin_login_time', 'unknown')
                }).eq('br_id', saque_id).execute()
                
                if response.data:
                    log_info("admin_marcar_saque_pago", f"Saque marcado como pago: ID {saque_id}")
                    return jsonify({'sucesso': True})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            except Exception as e:
                log_error("admin_marcar_saque_pago", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Atualizar em memória
            for saque in memory_storage['saques']:
                if saque.get('id') == int(saque_id):
                    saque['status'] = 'pago'
                    saque['data_pagamento'] = datetime.now().isoformat()
                    saque['admin_responsavel'] = session.get('admin_login_time', 'unknown')
                    log_info("admin_marcar_saque_pago", f"Saque marcado como pago em memória: ID {saque_id}")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
            
    except Exception as e:
        log_error("admin_marcar_saque_pago", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/bilhetes/<data_filtro>')
def admin_bilhetes(data_filtro):
    """Obtém bilhetes vendidos por data"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        bilhetes = []
        
        if supabase:
            try:
                response = supabase.table('ml_clientes').select('*').eq('ml_data_sorteio', data_filtro).order('ml_data_criacao', desc=True).execute()
                
                for b in (response.data or []):
                    bilhetes.append({
                        'nome': b['ml_nome'],
                        'telefone': b['ml_telefone'],
                        'chave_pix': b['ml_chave_pix'],
                        'bilhetes': b['ml_bilhetes'],
                        'payment_id': b['ml_payment_id'],
                        'data_sorteio': b['ml_data_sorteio']
                    })
            except Exception as e:
                log_error("admin_bilhetes", e)
        else:
            for b in memory_storage['clientes_ml']:
                if b.get('data_sorteio') == data_filtro:
                    bilhetes.append({
                        'nome': b['nome'],
                        'telefone': b['telefone'],
                        'chave_pix': b['chave_pix'],
                        'bilhetes': b['bilhetes'],
                        'payment_id': b['payment_id'],
                        'data_sorteio': b['data_sorteio']
                    })
        
        log_info("admin_bilhetes", f"Bilhetes consultados - Data: {data_filtro}, Total: {len(bilhetes)}")
        return jsonify({'bilhetes': bilhetes})
        
    except Exception as e:
        log_error("admin_bilhetes", e)
        return jsonify({'bilhetes': []})

@app.route('/admin/raspadinhas/<data_filtro>')
def admin_raspadinhas(data_filtro):
    """Obtém raspadinhas vendidas por data"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        vendas = []
        total_vendidas = 0
        total_usadas = 0
        
        if supabase:
            try:
                response = supabase.table('br_vendas').select('*').gte(
                    'br_data_criacao', data_filtro + ' 00:00:00'
                ).lt('br_data_criacao', data_filtro + ' 23:59:59').order('br_data_criacao', desc=True).execute()
                
                for v in (response.data or []):
                    vendas.append({
                        'payment_id': v['br_payment_id'],
                        'quantidade': v['br_quantidade'],
                        'valor_total': v['br_valor_total'],
                        'status': v['br_status'],
                        'raspadinhas_usadas': v.get('br_raspadinhas_usadas', 0),
                        'data_criacao': v['br_data_criacao'],
                        'ip_cliente': v.get('br_ip_cliente', 'N/A'),
                        'afiliado_nome': 'Via Afiliado' if v.get('br_afiliado_id') else 'Direto'
                    })
                    
                    if v['br_status'] == 'completed':
                        total_vendidas += v['br_quantidade']
                        total_usadas += v.get('br_raspadinhas_usadas', 0)
            except Exception as e:
                log_error("admin_raspadinhas", e)
        else:
            data_inicio = datetime.strptime(data_filtro, '%Y-%m-%d')
            data_fim = data_inicio + timedelta(days=1)
            
            for v in memory_storage['vendas_rb']:
                data_criacao = datetime.fromisoformat(v.get('data_criacao', ''))
                if data_inicio <= data_criacao < data_fim:
                    vendas.append({
                        'payment_id': v['payment_id'],
                        'quantidade': v['quantidade'],
                        'valor_total': v['valor_total'],
                        'status': v['status'],
                        'raspadinhas_usadas': v.get('raspadinhas_usadas', 0),
                        'data_criacao': v['data_criacao'],
                        'ip_cliente': v.get('ip_cliente', 'N/A'),
                        'afiliado_nome': 'Via Afiliado' if v.get('afiliado_id') else 'Direto'
                    })
                    
                    if v['status'] == 'completed':
                        total_vendidas += v['quantidade']
                        total_usadas += v.get('raspadinhas_usadas', 0)
        
        total_pendentes = total_vendidas - total_usadas
        
        estatisticas = {
            'total_vendidas': total_vendidas,
            'total_usadas': total_usadas,
            'total_pendentes': total_pendentes
        }
        
        log_info("admin_raspadinhas", f"Raspadinhas consultadas - Data: {data_filtro}, Vendas: {len(vendas)}")
        return jsonify({'vendas': vendas, 'estatisticas': estatisticas})
        
    except Exception as e:
        log_error("admin_raspadinhas", e)
        return jsonify({'vendas': [], 'estatisticas': {}})

@app.route('/admin/vendas')
def admin_vendas():
    """Obtém relatório de vendas para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        vendas = []
        sete_dias_atras = (datetime.now() - timedelta(days=7)).date().isoformat()
        
        if supabase:
            try:
                vendas_rb = supabase.table('br_vendas').select('*').gte('br_data_criacao', sete_dias_atras).eq('br_status', 'completed').execute()
                vendas_ml = supabase.table('ml_vendas').select('*').gte('ml_data_criacao', sete_dias_atras).eq('ml_status', 'completed').execute()
                
                for v in (vendas_rb.data or []):
                    vendas.append({
                        'payment_id': v['br_payment_id'],
                        'quantidade': v['br_quantidade'],
                        'valor': v['br_valor_total'],
                        'data': v['br_data_criacao'],
                        'jogo': 'Raspa Brasil',
                        'afiliado': bool(v.get('br_afiliado_id'))
                    })
                
                for v in (vendas_ml.data or []):
                    vendas.append({
                        'payment_id': v['ml_payment_id'],
                        'quantidade': v['ml_quantidade'],
                        'valor': v['ml_valor_total'],
                        'data': v['ml_data_criacao'],
                        'jogo': '2 para 1000',
                        'afiliado': bool(v.get('ml_afiliado_id'))
                    })
            except Exception as e:
                log_error("admin_vendas", e)
        else:
            data_limite = datetime.now() - timedelta(days=7)
            
            for v in memory_storage['vendas_rb']:
                if v.get('status') == 'completed':
                    data_venda = datetime.fromisoformat(v.get('data_criacao', ''))
                    if data_venda >= data_limite:
                        vendas.append({
                            'payment_id': v['payment_id'],
                            'quantidade': v['quantidade'],
                            'valor': v['valor_total'],
                            'data': v['data_criacao'],
                            'jogo': 'Raspa Brasil',
                            'afiliado': bool(v.get('afiliado_id'))
                        })
            
            for v in memory_storage['vendas_ml']:
                if v.get('status') == 'completed':
                    data_venda = datetime.fromisoformat(v.get('data_criacao', ''))
                    if data_venda >= data_limite:
                        vendas.append({
                            'payment_id': v['payment_id'],
                            'quantidade': v['quantidade'],
                            'valor': v['valor_total'],
                            'data': v['data_criacao'],
                            'jogo': '2 para 1000',
                            'afiliado': bool(v.get('afiliado_id'))
                        })
        
        # Ordenar por data
        vendas.sort(key=lambda x: x['data'], reverse=True)
        
        log_info("admin_vendas", f"Vendas consultadas: {len(vendas[:100])} dos últimos 7 dias")
        return jsonify({'vendas': vendas[:100]})
        
    except Exception as e:
        log_error("admin_vendas", e)
        return jsonify({'vendas': []})

@app.route('/admin/lista_ganhadores_dia/<data_filtro>')
def admin_lista_ganhadores_dia(data_filtro):
    """Gera lista de ganhadores do dia"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        ganhadores = []
        
        if supabase:
            try:
                # Ganhadores Raspa Brasil
                rb_response = supabase.table('br_ganhadores').select('*').gte(
                    'br_data_criacao', data_filtro + ' 00:00:00'
                ).lt('br_data_criacao', data_filtro + ' 23:59:59').execute()
                
                for g in (rb_response.data or []):
                    ganhadores.append({
                        'nome': g['br_nome'],
                        'valor': g['br_valor'],
                        'codigo': g['br_codigo'],
                        'data': g['br_data_criacao'],
                        'status': g['br_status_pagamento'],
                        'jogo': 'Raspa Brasil'
                    })
                
                # Ganhadores 2 para 1000
                ml_response = supabase.table('ml_ganhadores').select('*').eq('ml_data_sorteio', data_filtro).execute()
                
                for g in (ml_response.data or []):
                    ganhadores.append({
                        'nome': g['ml_nome'],
                        'valor': g['ml_valor'],
                        'milhar': g['ml_bilhete_premiado'],
                        'data': g['ml_data_sorteio'],
                        'status': g['ml_status_pagamento'],
                        'jogo': '2 para 1000'
                    })
            except Exception as e:
                log_error("admin_lista_ganhadores_dia", e)
        else:
            # Buscar em memória
            for g in memory_storage['ganhadores_rb']:
                if g.get('data_criacao', '')[:10] == data_filtro:
                    ganhadores.append({
                        'nome': g['nome'],
                        'valor': g['valor'],
                        'codigo': g['codigo'],
                        'data': g['data_criacao'],
                        'status': g['status_pagamento'],
                        'jogo': 'Raspa Brasil'
                    })
            
            for g in memory_storage['ganhadores_ml']:
                if g.get('data_sorteio') == data_filtro:
                    ganhadores.append({
                        'nome': g['nome'],
                        'valor': g['valor'],
                        'milhar': g['bilhete_premiado'],
                        'data': g['data_sorteio'],
                        'status': g['status_pagamento'],
                        'jogo': '2 para 1000'
                    })
        
        log_info("admin_lista_ganhadores_dia", f"Lista de ganhadores do dia {data_filtro}: {len(ganhadores)} encontrados")
        return jsonify({'ganhadores': ganhadores})
        
    except Exception as e:
        log_error("admin_lista_ganhadores_dia", e)
        return jsonify({'ganhadores': []})

# ========== ROTAS DE LOG E ERRO ==========

@app.route('/log_error', methods=['POST'])
def log_client_error():
    """Recebe erros do cliente JavaScript"""
    try:
        data = request.json
        log_error("client_error", data.get('error', 'Unknown error'), {
            'context': data.get('context'),
            'url': data.get('url'),
            'userAgent': data.get('userAgent'),
            'timestamp': data.get('timestamp')
        })
        return jsonify({'status': 'logged'}), 200
    except Exception as e:
        log_error("log_client_error", e)
        return jsonify({'error': 'Failed to log error'}), 500

# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando GANHA BRASIL - Sistema Integrado v2.2.0...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅ Real' if sdk else '🔄 Simulado'}")
    print(f"🔗 Supabase: {'✅ Conectado' if supabase else '🔄 Memória'}")
    print(f"📱 QR Code: {'✅ Disponível' if qrcode_available else '🔄 Texto'}")
    print(f"🎮 Jogos Disponíveis:")
    print(f"   - RASPA BRASIL: Raspadinhas virtuais (R$ {PRECO_RASPADINHA_RB:.2f})")
    print(f"   - 2 PARA 1000: Bilhetes da milhar (R$ {PRECO_BILHETE_ML:.2f})")
    print(f"👥 Sistema de Afiliados: ✅ COMPLETO")
    print(f"🎯 Prêmios: Manual (RB) + Sorteio diário (ML)")
    print(f"🔄 Pagamentos: Via PIX (real/simulado)")
    print(f"📱 Interface: Responsiva e moderna")
    print(f"🛡️ Segurança: Validações robustas")
    print(f"📊 Admin: Painel unificado completo")
    print(f"🔐 Senha Admin: {ADMIN_PASSWORD}")
    print(f"🎨 Frontend: Integração total com index.html")
    print(f"💾 Storage: Supabase com fallback em memória")
    print(f"🔧 MELHORIAS V2.2.0:")
    print(f"   ✅ Sistema de fallback em memória")
    print(f"   ✅ Pagamentos simulados quando MP indisponível")
    print(f"   ✅ QR Code generation local")
    print(f"   ✅ Logs de erros do cliente")
    print(f"   ✅ Sanitização de dados melhorada")
    print(f"   ✅ Validações mais robustas")
    print(f"   ✅ Sistema admin completamente funcional")
    print(f"   ✅ Afiliados com tracking completo")
    print(f"   ✅ Compatibilidade 100% com index.html")
    print(f"   ✅ Health check detalhado")
    print(f"   ✅ Error handling robusto")
    print(f"✅ SISTEMA TOTALMENTE FUNCIONAL E INTEGRADO!")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
