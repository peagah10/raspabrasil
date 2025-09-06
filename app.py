import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_from_directory, Response, render_template_string
from dotenv import load_dotenv
import json
import traceback
import base64
import io
import hashlib

# Inicializar bibliotecas opcionais
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

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    reportlab_available = True
except ImportError:
    reportlab_available = False
    print("⚠️ ReportLab não disponível - PDFs não serão gerados")

import uuid

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv('SECRET_KEY', 'ganha-brasil-2025-super-secret-key-v3')

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
APP_VERSION = "3.0.2"

# Sistema de armazenamento em memória (fallback quando Supabase não estiver disponível)
memory_storage = {
    'clientes': [],
    'vendas': [],
    'cliente_raspadinhas': [],
    'cliente_bilhetes': [],
    'ganhadores': [],
    'sorteios': [],
    'afiliados': [],
    'afiliado_clicks': [],
    'afiliado_vendas': [],
    'saques': [],
    'configuracoes': {
        'sistema_ativo': 'true',
        'premio_manual_liberado': '',
        'premio_acumulado': str(PREMIO_INICIAL_ML),
        'percentual_comissao_afiliado': str(PERCENTUAL_COMISSAO_AFILIADO)
    },
    'logs': []
}

# Inicializar cliente Supabase
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado com sucesso")
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

def hash_cpf(cpf):
    """Cria hash do CPF para usar como senha"""
    return hashlib.sha256(cpf.encode()).hexdigest()[:12]

def log_error(operation, error, extra_data=None):
    """Log de erros centralizado"""
    error_msg = f"❌ [{operation}] {str(error)}"
    print(error_msg)
    if extra_data:
        print(f"   Dados extras: {extra_data}")
    
    log_entry = {
        'id': len(memory_storage['logs']) + 1,
        'operacao': operation,
        'tipo': 'error',
        'mensagem': str(error)[:500],
        'dados_extras': json.dumps(extra_data) if extra_data else None,
        'timestamp': datetime.now().isoformat()
    }
    
    if supabase:
        try:
            supabase.table('gb_logs_sistema').insert({
                'gb_operacao': operation,
                'gb_tipo': 'error',
                'gb_mensagem': str(error)[:500],
                'gb_dados_extras': json.dumps(extra_data) if extra_data else None,
                'gb_ip_origem': request.remote_addr if request else None
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
    import time
    numero = random.randint(100000, 999999)
    timestamp = int(time.time()) % 1000  # últimos 3 dígitos do timestamp
    return f"AF{numero}{timestamp}"

def gerar_milhar():
    """Gera número aleatório de 4 dígitos entre 1111 e 9999"""
    return str(random.randint(1111, 9999))

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
            response = supabase.table('gb_configuracoes').select('gb_valor').eq('gb_chave', chave).execute()
            if response.data:
                return response.data[0]['gb_valor']
            return valor_padrao
        except Exception as e:
            log_error("obter_configuracao", e, {"chave": chave})
            return valor_padrao
    else:
        return memory_storage['configuracoes'].get(chave, valor_padrao)

def atualizar_configuracao(chave, valor, tipo='geral'):
    """Atualiza valor de configuração"""
    if supabase:
        try:
            response = supabase.table('gb_configuracoes').update({
                'gb_valor': str(valor),
                'gb_atualizado_em': datetime.now().isoformat()
            }).eq('gb_chave', chave).execute()
            
            if not response.data:
                response = supabase.table('gb_configuracoes').insert({
                    'gb_chave': chave,
                    'gb_valor': str(valor),
                    'gb_tipo': tipo
                }).execute()
            
            log_info("atualizar_configuracao", f"{chave} = {valor}")
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

def validar_session_cliente():
    """Valida se o cliente está logado"""
    return 'cliente_id' in session and 'cliente_cpf' in session

def obter_cliente_atual():
    """Obtém dados do cliente logado"""
    if not validar_session_cliente():
        return None
    
    cliente_id = session.get('cliente_id')
    
    if supabase:
        try:
            response = supabase.table('gb_clientes').select('*').eq('gb_id', cliente_id).execute()
            if response.data:
                return response.data[0]
        except:
            pass
    else:
        for cliente in memory_storage['clientes']:
            if cliente.get('id') == cliente_id:
                return cliente
    
    return None

def obter_total_vendas(tipo_jogo='raspa_brasil'):
    """Obtém total de vendas aprovadas"""
    if supabase:
        try:
            response = supabase.table('gb_vendas').select('gb_quantidade').eq('gb_tipo_jogo', tipo_jogo).eq('gb_status', 'completed').execute()
            if response.data:
                total = sum(venda['gb_quantidade'] for venda in response.data)
                return total
            return 0
        except Exception as e:
            log_error("obter_total_vendas", e, {"tipo_jogo": tipo_jogo})
            return 0
    else:
        vendas = memory_storage.get('vendas', [])
        total = sum(v['quantidade'] for v in vendas if v.get('tipo_jogo') == tipo_jogo and v.get('status') == 'completed')
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

def processar_comissao_afiliado(afiliado_id, valor_venda, venda_id):
    """Processa comissão do afiliado"""
    try:
        if not afiliado_id:
            return
            
        percentual = PERCENTUAL_COMISSAO_AFILIADO / 100
        comissao = valor_venda * percentual
        
        if supabase:
            try:
                # Buscar afiliado
                afiliado_response = supabase.table('gb_afiliados').select('*').eq('gb_id', afiliado_id).execute()
                if not afiliado_response.data:
                    return
                    
                afiliado = afiliado_response.data[0]
                
                # Atualizar estatísticas do afiliado
                novo_total_vendas = (afiliado.get('gb_total_vendas', 0) or 0) + 1
                nova_comissao_total = (afiliado.get('gb_total_comissao', 0) or 0) + comissao
                novo_saldo = (afiliado.get('gb_saldo_disponivel', 0) or 0) + comissao
                
                supabase.table('gb_afiliados').update({
                    'gb_total_vendas': novo_total_vendas,
                    'gb_total_comissao': nova_comissao_total,
                    'gb_saldo_disponivel': novo_saldo
                }).eq('gb_id', afiliado_id).execute()
                
                # Registrar venda do afiliado
                supabase.table('gb_afiliado_vendas').insert({
                    'gb_afiliado_id': afiliado_id,
                    'gb_venda_id': venda_id,
                    'gb_comissao': comissao,
                    'gb_status': 'aprovada'
                }).execute()
                
                log_info("processar_comissao_afiliado", 
                        f"Comissão processada: Afiliado {afiliado_id} - R$ {comissao:.2f}")
                        
            except Exception as e:
                log_error("processar_comissao_afiliado", e)
        else:
            # Processar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('id') == afiliado_id:
                    afiliado['total_vendas'] = afiliado.get('total_vendas', 0) + 1
                    afiliado['total_comissao'] = afiliado.get('total_comissao', 0) + comissao
                    afiliado['saldo_disponivel'] = afiliado.get('saldo_disponivel', 0) + comissao
                    
                    memory_storage['afiliado_vendas'].append({
                        'id': len(memory_storage['afiliado_vendas']) + 1,
                        'afiliado_id': afiliado_id,
                        'venda_id': venda_id,
                        'comissao': comissao,
                        'status': 'aprovada',
                        'data_venda': datetime.now().isoformat()
                    })
                    
                    log_info("processar_comissao_afiliado", 
                            f"Comissão processada em memória: Afiliado {afiliado_id} - R$ {comissao:.2f}")
                    break
                    
    except Exception as e:
        log_error("processar_comissao_afiliado", e)

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
            
            # Registrar clique do afiliado
            if supabase:
                try:
                    afiliado = supabase.table('gb_afiliados').select('gb_id').eq('gb_codigo', ref_code).execute()
                    if afiliado.data:
                        supabase.table('gb_afiliado_clicks').insert({
                            'gb_afiliado_id': afiliado.data[0]['gb_id'],
                            'gb_ip_visitor': request.remote_addr or 'unknown',
                            'gb_user_agent': request.headers.get('User-Agent', '')[:500],
                            'gb_referrer': request.headers.get('Referer', '')[:500]
                        }).execute()
                        
                        # Incrementar contador
                        current_clicks = supabase.table('gb_afiliados').select('gb_total_clicks').eq('gb_id', afiliado.data[0]['gb_id']).execute()
                        new_clicks = (current_clicks.data[0]['gb_total_clicks'] or 0) + 1 if current_clicks.data else 1
                        
                        supabase.table('gb_afiliados').update({
                            'gb_total_clicks': new_clicks
                        }).eq('gb_id', afiliado.data[0]['gb_id']).execute()
                except:
                    pass
        
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
        hoje = date.today().isoformat()
        
        # Estatísticas básicas
        stats = {
            'vendas_rb_hoje': 0,
            'vendas_ml_hoje': 0,
            'total_clientes': 0,
            'total_afiliados': 0,
            'sistema_funcionando': True
        }
        
        # Tentar obter estatísticas do banco
        if supabase:
            try:
                # Vendas RB hoje
                rb_hoje = supabase.table('gb_vendas').select('gb_quantidade').gte(
                    'gb_data_criacao', hoje + ' 00:00:00'
                ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', 'raspa_brasil').eq('gb_status', 'completed').execute()
                stats['vendas_rb_hoje'] = sum(v['gb_quantidade'] for v in (rb_hoje.data or []))
                
                # Vendas ML hoje
                ml_hoje = supabase.table('gb_vendas').select('gb_quantidade').gte(
                    'gb_data_criacao', hoje + ' 00:00:00'
                ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', '2para1000').eq('gb_status', 'completed').execute()
                stats['vendas_ml_hoje'] = sum(v['gb_quantidade'] for v in (ml_hoje.data or []))
                
                # Total clientes
                clientes = supabase.table('gb_clientes').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['total_clientes'] = len(clientes.data or [])
                
                # Total afiliados
                afiliados = supabase.table('gb_afiliados').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['total_afiliados'] = len(afiliados.data or [])
                
            except Exception as e:
                log_error("health_check_stats", e)
                stats['sistema_funcionando'] = False
        else:
            # Estatísticas da memória
            stats['vendas_rb_hoje'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == 'raspa_brasil'])
            stats['vendas_ml_hoje'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == '2para1000'])
            stats['total_clientes'] = len([c for c in memory_storage['clientes'] if c.get('status') == 'ativo'])
            stats['total_afiliados'] = len([a for a in memory_storage['afiliados'] if a.get('status') == 'ativo'])
        
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'services': {
                'supabase': supabase is not None,
                'mercadopago': sdk is not None,
                'flask': True,
                'qrcode': qrcode_available,
                'reportlab': reportlab_available
            },
            'games': ['raspa_brasil', '2para1000'],
            'features': [
                'login_clientes',
                'area_cliente',
                'minhas_raspadinhas',
                'meus_bilhetes',
                'afiliados',
                'admin_completo',
                'pagamentos_unificados',
                'sistema_manual_premios',
                'storage_fallback',
                'qr_code_generation',
                'comissoes_automaticas',
                'relatorios_completos',
                'ganhadores_management',
                'pdf_generation'
            ],
            'configuration': {
                'total_raspadinhas': TOTAL_RASPADINHAS,
                'premio_inicial_ml': PREMIO_INICIAL_ML,
                'preco_raspadinha': PRECO_RASPADINHA_RB,
                'preco_bilhete': PRECO_BILHETE_ML,
                'comissao_afiliado': PERCENTUAL_COMISSAO_AFILIADO
            },
            'statistics': stats
        }
    except Exception as e:
        log_error("health_check", e)
        return {'status': 'error', 'error': str(e)}, 500

# ========== ROTAS DE CLIENTE (LOGIN/CADASTRO) ==========

@app.route('/cliente/cadastrar', methods=['POST'])
def cliente_cadastrar():
    """Cadastra novo cliente"""
    try:
        data = sanitizar_dados_entrada(request.json)
        
        nome = data.get('nome', '').strip()
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        telefone = data.get('telefone', '').strip()
        email = data.get('email', '').strip()
        
        # Validações
        if not nome or len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        cliente_data = {
            'nome': nome[:255],
            'cpf': cpf,
            'telefone': telefone[:20] if telefone else None,
            'email': email[:255] if email else None,
            'status': 'ativo',
            'ip_cadastro': request.remote_addr or 'unknown',
            'data_cadastro': datetime.now().isoformat()
        }
        
        if supabase:
            try:
                # Verificar se CPF já existe
                existing = supabase.table('gb_clientes').select('gb_id').eq('gb_cpf', cpf).execute()
                if existing.data:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
                
                response = supabase.table('gb_clientes').insert({
                    'gb_nome': nome[:255],
                    'gb_cpf': cpf,
                    'gb_telefone': telefone[:20] if telefone else None,
                    'gb_email': email[:255] if email else None,
                    'gb_status': 'ativo',
                    'gb_ip_cadastro': request.remote_addr or 'unknown'
                }).execute()
                
                if response.data:
                    cliente = response.data[0]
                    # Fazer login automático
                    session['cliente_id'] = cliente['gb_id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = nome
                    
                    log_info("cliente_cadastrar", f"Novo cliente cadastrado: {nome} - CPF: {cpf[:3]}***")
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['gb_id'],
                            'nome': nome,
                            'cpf': cpf
                        }
                    })
                    
            except Exception as e:
                log_error("cliente_cadastrar", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Verificar duplicata em memória
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
            
            cliente_data['id'] = len(memory_storage['clientes']) + 1
            memory_storage['clientes'].append(cliente_data)
            
            # Fazer login automático
            session['cliente_id'] = cliente_data['id']
            session['cliente_cpf'] = cpf
            session['cliente_nome'] = nome
            
            log_info("cliente_cadastrar", f"Cliente cadastrado em memória: {nome}")
            return jsonify({
                'sucesso': True,
                'cliente': {
                    'id': cliente_data['id'],
                    'nome': nome,
                    'cpf': cpf
                }
            })
            
    except Exception as e:
        log_error("cliente_cadastrar", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/cliente/login', methods=['POST'])
def cliente_login():
    """Login do cliente por CPF"""
    try:
        data = sanitizar_dados_entrada(request.json)
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        if supabase:
            try:
                response = supabase.table('gb_clientes').select('*').eq('gb_cpf', cpf).eq('gb_status', 'ativo').execute()
                
                if response.data:
                    cliente = response.data[0]
                    
                    # Atualizar último acesso
                    supabase.table('gb_clientes').update({
                        'gb_ultimo_acesso': datetime.now().isoformat()
                    }).eq('gb_id', cliente['gb_id']).execute()
                    
                    # Criar sessão
                    session['cliente_id'] = cliente['gb_id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = cliente['gb_nome']
                    
                    log_info("cliente_login", f"Cliente logado: {cliente['gb_nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['gb_id'],
                            'nome': cliente['gb_nome'],
                            'cpf': cpf
                        }
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
                    
            except Exception as e:
                log_error("cliente_login", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Buscar em memória
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf and cliente.get('status') == 'ativo':
                    # Criar sessão
                    session['cliente_id'] = cliente['id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = cliente['nome']
                    
                    cliente['ultimo_acesso'] = datetime.now().isoformat()
                    
                    log_info("cliente_login", f"Cliente logado em memória: {cliente['nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['id'],
                            'nome': cliente['nome'],
                            'cpf': cpf
                        }
                    })
            
            return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
            
    except Exception as e:
        log_error("cliente_login", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/cliente/logout')
def cliente_logout():
    """Logout do cliente"""
    try:
        session.pop('cliente_id', None)
        session.pop('cliente_cpf', None)
        session.pop('cliente_nome', None)
        
        log_info("cliente_logout", "Cliente deslogado")
        return jsonify({'sucesso': True})
        
    except Exception as e:
        log_error("cliente_logout", e)
        return jsonify({'sucesso': False, 'erro': 'Erro ao fazer logout'})

@app.route('/cliente/verificar_login')
def cliente_verificar_login():
    """Verifica se o cliente está logado"""
    try:
        if validar_session_cliente():
            return jsonify({
                'logado': True,
                'cliente': {
                    'id': session.get('cliente_id'),
                    'nome': session.get('cliente_nome'),
                    'cpf': session.get('cliente_cpf')
                }
            })
        else:
            return jsonify({'logado': False})
            
    except Exception as e:
        log_error("cliente_verificar_login", e)
        return jsonify({'logado': False})

@app.route('/cliente/minhas_raspadinhas')
def cliente_minhas_raspadinhas():
    """Obtém raspadinhas do cliente logado"""
    try:
        if not validar_session_cliente():
            return jsonify({'erro': 'Não autorizado'}), 401
        
        cliente_id = session.get('cliente_id')
        raspadinhas = []
        
        if supabase:
            try:
                # Buscar vendas do cliente
                vendas = supabase.table('gb_vendas').select('*').eq(
                    'gb_cliente_id', cliente_id
                ).eq('gb_tipo_jogo', 'raspa_brasil').eq('gb_status', 'completed').order(
                    'gb_data_criacao', desc=True
                ).execute()
                
                for venda in (vendas.data or []):
                    # Buscar raspadinhas desta venda
                    rasp_response = supabase.table('gb_cliente_raspadinhas').select('*').eq(
                        'gb_venda_id', venda['gb_id']
                    ).order('gb_numero_raspadinha').execute()
                    
                    raspadinhas.append({
                        'venda_id': venda['gb_id'],
                        'payment_id': venda['gb_payment_id'],
                        'quantidade': venda['gb_quantidade'],
                        'data_compra': venda['gb_data_criacao'],
                        'raspadinhas': [{
                            'id': r['gb_id'],
                            'numero': r['gb_numero_raspadinha'],
                            'status': r['gb_status'],
                            'premio': r.get('gb_premio'),
                            'codigo': r.get('gb_codigo_premio'),
                            'data_raspagem': r.get('gb_data_raspagem')
                        } for r in (rasp_response.data or [])]
                    })
                    
            except Exception as e:
                log_error("cliente_minhas_raspadinhas", e)
        else:
            # Buscar em memória
            for venda in memory_storage['vendas']:
                if venda.get('cliente_id') == cliente_id and venda.get('tipo_jogo') == 'raspa_brasil' and venda.get('status') == 'completed':
                    rasp_list = []
                    for rasp in memory_storage['cliente_raspadinhas']:
                        if rasp.get('venda_id') == venda['id']:
                            rasp_list.append({
                                'id': rasp['id'],
                                'numero': rasp['numero_raspadinha'],
                                'status': rasp['status'],
                                'premio': rasp.get('premio'),
                                'codigo': rasp.get('codigo_premio'),
                                'data_raspagem': rasp.get('data_raspagem')
                            })
                    
                    raspadinhas.append({
                        'venda_id': venda['id'],
                        'payment_id': venda['payment_id'],
                        'quantidade': venda['quantidade'],
                        'data_compra': venda['data_criacao'],
                        'raspadinhas': rasp_list
                    })
        
        return jsonify({'raspadinhas': raspadinhas})
        
    except Exception as e:
        log_error("cliente_minhas_raspadinhas", e)
        return jsonify({'erro': 'Erro ao buscar raspadinhas'}), 500

@app.route('/cliente/meus_bilhetes')
def cliente_meus_bilhetes():
    """Obtém bilhetes do cliente logado"""
    try:
        if not validar_session_cliente():
            return jsonify({'erro': 'Não autorizado'}), 401
        
        cliente_id = session.get('cliente_id')
        bilhetes = []
        
        if supabase:
            try:
                # Buscar vendas do cliente
                vendas = supabase.table('gb_vendas').select('*').eq(
                    'gb_cliente_id', cliente_id
                ).eq('gb_tipo_jogo', '2para1000').eq('gb_status', 'completed').order(
                    'gb_data_criacao', desc=True
                ).execute()
                
                for venda in (vendas.data or []):
                    # Buscar bilhetes desta venda
                    bilh_response = supabase.table('gb_cliente_bilhetes').select('*').eq(
                        'gb_venda_id', venda['gb_id']
                    ).order('gb_numero_bilhete').execute()
                    
                    bilhetes.append({
                        'venda_id': venda['gb_id'],
                        'payment_id': venda['gb_payment_id'],
                        'quantidade': venda['gb_quantidade'],
                        'data_compra': venda['gb_data_criacao'],
                        'bilhetes': [{
                            'id': b['gb_id'],
                            'numero': b['gb_numero_bilhete'],
                            'data_sorteio': b['gb_data_sorteio'],
                            'status': b['gb_status'],
                            'premio_ganho': b.get('gb_premio_ganho')
                        } for b in (bilh_response.data or [])]
                    })
                    
            except Exception as e:
                log_error("cliente_meus_bilhetes", e)
        else:
            # Buscar em memória
            for venda in memory_storage['vendas']:
                if venda.get('cliente_id') == cliente_id and venda.get('tipo_jogo') == '2para1000' and venda.get('status') == 'completed':
                    bilh_list = []
                    for bilh in memory_storage['cliente_bilhetes']:
                        if bilh.get('venda_id') == venda['id']:
                            bilh_list.append({
                                'id': bilh['id'],
                                'numero': bilh['numero_bilhete'],
                                'data_sorteio': bilh['data_sorteio'],
                                'status': bilh['status'],
                                'premio_ganho': bilh.get('premio_ganho')
                            })
                    
                    bilhetes.append({
                        'venda_id': venda['id'],
                        'payment_id': venda['payment_id'],
                        'quantidade': venda['quantidade'],
                        'data_compra': venda['data_criacao'],
                        'bilhetes': bilh_list
                    })
        
        return jsonify({'bilhetes': bilhetes})
        
    except Exception as e:
        log_error("cliente_meus_bilhetes", e)
        return jsonify({'erro': 'Erro ao buscar bilhetes'}), 500

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

        # Verificar se cliente está logado
        if not validar_session_cliente():
            return jsonify({'error': 'Faça login primeiro para continuar'}), 401

        cliente_id = session.get('cliente_id')

        # Calcular preço
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        total = quantidade * preco_unitario

        log_info("create_payment", f"Criando pagamento: {game_type} - {quantidade} unidades - R$ {total:.2f} - Cliente ID: {cliente_id}")

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
                    response = supabase.table('gb_afiliados').select('*').eq('gb_codigo', afiliado_codigo).eq('gb_status', 'ativo').execute()
                    if response.data:
                        afiliado_id = response.data[0]['gb_id']
                        log_info("create_payment", f"Venda com afiliado: {response.data[0]['gb_nome']}")
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
                    "external_reference": f"{game_type.upper()}_{int(datetime.now().timestamp())}_{quantidade}_{cliente_id}"
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
            'cliente_id': cliente_id,
            'afiliado_id': afiliado_id,
            'tipo_jogo': game_type,
            'quantidade': quantidade,
            'valor_total': total,
            'status': 'pending',
            'raspadinhas_usadas': 0 if game_type == 'raspa_brasil' else None,
            'ip_cliente': request.remote_addr or 'unknown',
            'user_agent': request.headers.get('User-Agent', '')[:500],
            'data_criacao': datetime.now().isoformat()
        }

        if supabase:
            try:
                db_data = {
                    'gb_payment_id': payment_id,
                    'gb_cliente_id': cliente_id,
                    'gb_tipo_jogo': game_type,
                    'gb_quantidade': quantidade,
                    'gb_valor_total': total,
                    'gb_status': 'pending',
                    'gb_ip_cliente': request.remote_addr or 'unknown',
                    'gb_user_agent': request.headers.get('User-Agent', '')[:500]
                }
                
                if afiliado_id:
                    db_data['gb_afiliado_id'] = afiliado_id
                
                if game_type == 'raspa_brasil':
                    db_data['gb_raspadinhas_usadas'] = 0
                
                response = supabase.table('gb_vendas').insert(db_data).execute()
                
                if response.data:
                    venda_id = response.data[0]['gb_id']
                    session['venda_id'] = venda_id
                    
                    # Criar registros de raspadinhas ou bilhetes
                    if game_type == 'raspa_brasil':
                        quantidade_real = 12 if quantidade == 10 else quantidade
                        for i in range(quantidade_real):
                            supabase.table('gb_cliente_raspadinhas').insert({
                                'gb_cliente_id': cliente_id,
                                'gb_venda_id': venda_id,
                                'gb_numero_raspadinha': i + 1,
                                'gb_status': 'disponivel'
                            }).execute()
                    
                    log_info("create_payment", f"Venda salva no Supabase: {payment_id}")
                    
            except Exception as e:
                log_error("create_payment_save", e, {"payment_id": payment_id})
        else:
            # Salvar em memória
            venda_data['id'] = len(memory_storage['vendas']) + 1
            memory_storage['vendas'].append(venda_data)
            session['venda_id'] = venda_data['id']
            
            # Criar registros de raspadinhas ou bilhetes
            if game_type == 'raspa_brasil':
                quantidade_real = 12 if quantidade == 10 else quantidade
                for i in range(quantidade_real):
                    memory_storage['cliente_raspadinhas'].append({
                        'id': len(memory_storage['cliente_raspadinhas']) + 1,
                        'cliente_id': cliente_id,
                        'venda_id': venda_data['id'],
                        'numero_raspadinha': i + 1,
                        'status': 'disponivel'
                    })
            
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
        afiliado_id = session.get('afiliado_id')
        quantidade = session.get('quantidade', 0)
        venda_id = session.get('venda_id')
        
        # Calcular valor total
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        valor_total = quantidade * preco_unitario
        
        # Atualizar no banco
        if supabase:
            try:
                update_data = {
                    'gb_status': 'completed',
                    'gb_data_aprovacao': datetime.now().isoformat()
                }
                
                supabase.table('gb_vendas').update(update_data).eq('gb_payment_id', str(payment_id)).execute()
                log_info("processar_pagamento_aprovado", f"Status atualizado no Supabase: {payment_id}")
                
            except Exception as e:
                log_error("processar_pagamento_aprovado", e, {"payment_id": payment_id})
        else:
            # Atualizar em memória
            for venda in memory_storage['vendas']:
                if venda.get('payment_id') == payment_id:
                    venda['status'] = 'completed'
                    venda['data_aprovacao'] = datetime.now().isoformat()
                    log_info("processar_pagamento_aprovado", f"Status atualizado em memória: {payment_id}")
                    break
        
        # Processar comissão do afiliado
        if afiliado_id and venda_id:
            processar_comissao_afiliado(afiliado_id, valor_total, venda_id)

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
        if not validar_session_cliente():
            return jsonify({'erro': 'Faça login para raspar'}), 401
        
        data = sanitizar_dados_entrada(request.json)
        raspadinha_id = data.get('raspadinha_id')
        
        if not raspadinha_id:
            return jsonify({'erro': 'ID da raspadinha é obrigatório'}), 400
        
        cliente_id = session.get('cliente_id')
        
        if supabase:
            try:
                # Verificar se a raspadinha pertence ao cliente e está disponível
                rasp = supabase.table('gb_cliente_raspadinhas').select('*').eq(
                    'gb_id', raspadinha_id
                ).eq('gb_cliente_id', cliente_id).eq('gb_status', 'disponivel').execute()
                
                if not rasp.data:
                    return jsonify({'erro': 'Raspadinha não encontrada ou já foi raspada'}), 400
                
                # Verificar se há prêmio liberado pelo admin
                premio = sortear_premio_novo_sistema()
                
                if premio:
                    codigo = gerar_codigo_antifraude()
                    
                    # Atualizar raspadinha
                    supabase.table('gb_cliente_raspadinhas').update({
                        'gb_status': 'premiada',
                        'gb_premio': premio,
                        'gb_codigo_premio': codigo,
                        'gb_data_raspagem': datetime.now().isoformat(),
                        'gb_ip_raspagem': request.remote_addr or 'unknown'
                    }).eq('gb_id', raspadinha_id).execute()
                    
                    # Atualizar contador na venda
                    venda_id = rasp.data[0]['gb_venda_id']
                    venda = supabase.table('gb_vendas').select('gb_raspadinhas_usadas').eq('gb_id', venda_id).execute()
                    if venda.data:
                        novo_contador = (venda.data[0]['gb_raspadinhas_usadas'] or 0) + 1
                        supabase.table('gb_vendas').update({
                            'gb_raspadinhas_usadas': novo_contador
                        }).eq('gb_id', venda_id).execute()
                    
                    log_info("raspar", f"PRÊMIO LIBERADO: {premio} - Código: {codigo} - Cliente: {cliente_id}")
                    
                    return jsonify({
                        'ganhou': True,
                        'valor': premio,
                        'codigo': codigo
                    })
                else:
                    # Atualizar raspadinha como raspada sem prêmio
                    supabase.table('gb_cliente_raspadinhas').update({
                        'gb_status': 'raspada',
                        'gb_data_raspagem': datetime.now().isoformat(),
                        'gb_ip_raspagem': request.remote_addr or 'unknown'
                    }).eq('gb_id', raspadinha_id).execute()
                    
                    # Atualizar contador na venda
                    venda_id = rasp.data[0]['gb_venda_id']
                    venda = supabase.table('gb_vendas').select('gb_raspadinhas_usadas').eq('gb_id', venda_id).execute()
                    if venda.data:
                        novo_contador = (venda.data[0]['gb_raspadinhas_usadas'] or 0) + 1
                        supabase.table('gb_vendas').update({
                            'gb_raspadinhas_usadas': novo_contador
                        }).eq('gb_id', venda_id).execute()
                    
                    log_info("raspar", f"Sem prêmio - Cliente: {cliente_id}")
                    
                    return jsonify({'ganhou': False})
                    
            except Exception as e:
                log_error("raspar", e)
                return jsonify({'erro': 'Erro ao processar raspagem'}), 500
        else:
            # Processar em memória
            raspadinha = None
            for rasp in memory_storage['cliente_raspadinhas']:
                if rasp.get('id') == int(raspadinha_id) and rasp.get('cliente_id') == cliente_id and rasp.get('status') == 'disponivel':
                    raspadinha = rasp
                    break
            
            if not raspadinha:
                return jsonify({'erro': 'Raspadinha não encontrada ou já foi raspada'}), 400
            
            # Verificar se há prêmio liberado pelo admin
            premio = sortear_premio_novo_sistema()
            
            if premio:
                codigo = gerar_codigo_antifraude()
                
                # Atualizar raspadinha
                raspadinha['status'] = 'premiada'
                raspadinha['premio'] = premio
                raspadinha['codigo_premio'] = codigo
                raspadinha['data_raspagem'] = datetime.now().isoformat()
                raspadinha['ip_raspagem'] = request.remote_addr or 'unknown'
                
                # Atualizar contador na venda
                for venda in memory_storage['vendas']:
                    if venda.get('id') == raspadinha['venda_id']:
                        venda['raspadinhas_usadas'] = venda.get('raspadinhas_usadas', 0) + 1
                        break
                
                log_info("raspar", f"PRÊMIO LIBERADO (memória): {premio} - Código: {codigo}")
                
                return jsonify({
                    'ganhou': True,
                    'valor': premio,
                    'codigo': codigo
                })
            else:
                # Atualizar raspadinha como raspada sem prêmio
                raspadinha['status'] = 'raspada'
                raspadinha['data_raspagem'] = datetime.now().isoformat()
                raspadinha['ip_raspagem'] = request.remote_addr or 'unknown'
                
                # Atualizar contador na venda
                for venda in memory_storage['vendas']:
                    if venda.get('id') == raspadinha['venda_id']:
                        venda['raspadinhas_usadas'] = venda.get('raspadinhas_usadas', 0) + 1
                        break
                
                return jsonify({'ganhou': False})

    except Exception as e:
        log_error("raspar", e)
        return jsonify({'erro': 'Erro interno do servidor'}), 500

@app.route('/salvar_ganhador', methods=['POST'])
def salvar_ganhador():
    """Salva dados do ganhador"""
    try:
        if not validar_session_cliente():
            return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 401
        
        data = sanitizar_dados_entrada(request.json)
        cliente_id = session.get('cliente_id')

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
            'cliente_id': cliente_id,
            'tipo_jogo': 'raspa_brasil',
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
                existing = supabase.table('gb_ganhadores').select('gb_id').eq('gb_codigo_premio', data['codigo']).execute()
                if existing.data:
                    return jsonify({'sucesso': False, 'erro': 'Código já utilizado'})

                response = supabase.table('gb_ganhadores').insert({
                    'gb_cliente_id': cliente_id,
                    'gb_tipo_jogo': 'raspa_brasil',
                    'gb_codigo_premio': data['codigo'],
                    'gb_nome': data['nome'].strip()[:255],
                    'gb_valor': data['valor'],
                    'gb_chave_pix': data['chave_pix'].strip()[:255],
                    'gb_tipo_chave_pix': data['tipo_chave'],
                    'gb_status_pagamento': 'pendente',
                    'gb_ip_cliente': request.remote_addr or 'unknown'
                }).execute()

                if response.data:
                    log_info("salvar_ganhador", f"Ganhador salvo: {data['nome']} - {data['valor']}")
                    return jsonify({'sucesso': True, 'id': response.data[0]['gb_id']})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao inserir ganhador'})
            except Exception as e:
                log_error("salvar_ganhador", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Verificar duplicata em memória
            for ganhador in memory_storage['ganhadores']:
                if ganhador.get('codigo') == data['codigo']:
                    return jsonify({'sucesso': False, 'erro': 'Código já utilizado'})
            
            ganhador_data['id'] = len(memory_storage['ganhadores']) + 1
            memory_storage['ganhadores'].append(ganhador_data)
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
        if not validar_session_cliente():
            return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 401
        
        data = sanitizar_dados_entrada(request.json)
        cliente_id = session.get('cliente_id')
        venda_id = session.get('venda_id')

        campos_obrigatorios = ['nome', 'telefone', 'chave_pix']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'sucesso': False, 'erro': f'Campo {campo} é obrigatório'})

        # Validações
        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        if len(data['telefone']) < 10:
            return jsonify({'sucesso': False, 'erro': 'Telefone inválido'})

        payment_id = data.get('payment_id') or session.get('payment_id')
        if not payment_id:
            return jsonify({'sucesso': False, 'erro': 'Payment ID não encontrado'})

        # Atualizar dados do cliente
        if supabase:
            try:
                # Atualizar telefone e chave PIX do cliente
                supabase.table('gb_clientes').update({
                    'gb_telefone': data['telefone'].strip()[:20],
                    'gb_chave_pix': data['chave_pix'].strip()[:255],
                    'gb_tipo_chave_pix': data.get('tipo_chave_pix', 'cpf')
                }).eq('gb_id', cliente_id).execute()
                
                # Buscar bilhetes gerados
                bilhetes = supabase.table('gb_cliente_bilhetes').select('gb_numero_bilhete').eq(
                    'gb_venda_id', venda_id
                ).execute()
                
                numeros_bilhetes = [b['gb_numero_bilhete'] for b in (bilhetes.data or [])]
                
                log_info("enviar_bilhete", f"Bilhetes confirmados: {numeros_bilhetes} - Cliente: {data['nome']}")
                
                return jsonify({
                    'sucesso': True,
                    'bilhetes': numeros_bilhetes
                })
                
            except Exception as e:
                log_error("enviar_bilhete", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Atualizar em memória
            for cliente in memory_storage['clientes']:
                if cliente.get('id') == cliente_id:
                    cliente['telefone'] = data['telefone'].strip()[:20]
                    cliente['chave_pix'] = data['chave_pix'].strip()[:255]
                    cliente['tipo_chave_pix'] = data.get('tipo_chave_pix', 'cpf')
                    break
            
            # Buscar bilhetes
            numeros_bilhetes = []
            for bilhete in memory_storage['cliente_bilhetes']:
                if bilhete.get('venda_id') == venda_id:
                    numeros_bilhetes.append(bilhete['numero_bilhete'])
            
            log_info("enviar_bilhete", f"Bilhetes confirmados em memória: {numeros_bilhetes}")
            
            return jsonify({
                'sucesso': True,
                'bilhetes': numeros_bilhetes
            })

    except Exception as e:
        log_error("enviar_bilhete", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/gerar_bilhetes_ml', methods=['POST'])
def gerar_bilhetes_ml():
    """Gera bilhetes para o cliente após pagamento aprovado"""
    try:
        if not validar_session_cliente():
            return jsonify({'erro': 'Não autorizado'}), 401
        
        venda_id = session.get('venda_id')
        quantidade = session.get('quantidade', 0)
        cliente_id = session.get('cliente_id')
        
        if not venda_id or quantidade == 0:
            return jsonify({'erro': 'Dados de venda não encontrados'}), 400
        
        bilhetes_gerados = []
        hoje = date.today().isoformat()
        
        if supabase:
            try:
                # Gerar bilhetes únicos
                for i in range(quantidade):
                    numero = gerar_milhar()
                    
                    supabase.table('gb_cliente_bilhetes').insert({
                        'gb_cliente_id': cliente_id,
                        'gb_venda_id': venda_id,
                        'gb_numero_bilhete': numero,
                        'gb_data_sorteio': hoje,
                        'gb_status': 'ativo'
                    }).execute()
                    
                    bilhetes_gerados.append(numero)
                
                log_info("gerar_bilhetes_ml", f"Bilhetes gerados: {bilhetes_gerados}")
                
            except Exception as e:
                log_error("gerar_bilhetes_ml", e)
                return jsonify({'erro': 'Erro ao gerar bilhetes'}), 500
        else:
            # Gerar em memória
            for i in range(quantidade):
                numero = gerar_milhar()
                
                memory_storage['cliente_bilhetes'].append({
                    'id': len(memory_storage['cliente_bilhetes']) + 1,
                    'cliente_id': cliente_id,
                    'venda_id': venda_id,
                    'numero_bilhete': numero,
                    'data_sorteio': hoje,
                    'status': 'ativo'
                })
                
                bilhetes_gerados.append(numero)
            
            log_info("gerar_bilhetes_ml", f"Bilhetes gerados em memória: {bilhetes_gerados}")
        
        return jsonify({
            'sucesso': True,
            'bilhetes': bilhetes_gerados
        })
        
    except Exception as e:
        log_error("gerar_bilhetes_ml", e)
        return jsonify({'erro': 'Erro ao gerar bilhetes'}), 500

@app.route('/resultado_sorteio')
def resultado_sorteio():
    """Obtém resultado do sorteio do dia do 2 para 1000 - CORRIGIDO"""
    try:
        hoje = date.today().isoformat()
        valor_acumulado = obter_premio_acumulado()
        
        if supabase:
            try:
                response = supabase.table('gb_sorteios').select('*').eq('gb_data_sorteio', hoje).execute()

                if response.data:
                    sorteio = response.data[0]
                    log_info("resultado_sorteio", f"Resultado: {sorteio['gb_milhar_sorteada']}")
                    
                    return jsonify({
                        'milhar_sorteada': sorteio['gb_milhar_sorteada'],
                        'houve_ganhador': sorteio['gb_houve_ganhador'],
                        'valor_premio': f"R$ {sorteio.get('gb_valor_premio', 0):.2f}".replace('.', ',') if sorteio.get('gb_valor_premio') else '',
                        'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ','),
                        'ganhador_nome': sorteio.get('gb_ganhador_nome', ''),
                        'observacoes': sorteio.get('gb_observacoes', '')
                    })
            except Exception as e:
                log_error("resultado_sorteio", e)
        else:
            # Verificar em memória
            for sorteio in memory_storage['sorteios']:
                if sorteio.get('data_sorteio') == hoje:
                    return jsonify({
                        'milhar_sorteada': sorteio['milhar_sorteada'],
                        'houve_ganhador': sorteio['houve_ganhador'],
                        'valor_premio': f"R$ {sorteio.get('valor_premio', 0):.2f}".replace('.', ',') if sorteio.get('valor_premio') else '',
                        'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ','),
                        'ganhador_nome': sorteio.get('ganhador_nome', ''),
                        'observacoes': sorteio.get('observacoes', '')
                    })
        
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ','),
            'ganhador_nome': '',
            'observacoes': ''
        })

    except Exception as e:
        log_error("resultado_sorteio", e)
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{PREMIO_INICIAL_ML:.2f}".replace('.', ','),
            'ganhador_nome': '',
            'observacoes': ''
        })

@app.route('/ultimos_ganhadores')
def ultimos_ganhadores():
    """Obtém últimos ganhadores do 2 para 1000"""
    try:
        ganhadores = []
        
        if supabase:
            try:
                response = supabase.table('gb_ganhadores').select(
                    'gb_nome, gb_valor, gb_bilhete_premiado, gb_data_criacao'
                ).eq('gb_tipo_jogo', '2para1000').order('gb_data_criacao', desc=True).limit(10).execute()

                for ganhador in (response.data or []):
                    nome_display = ganhador['gb_nome']
                    if len(nome_display) > 15:
                        nome_display = nome_display[:15] + '...'
                    
                    ganhadores.append({
                        'nome': nome_display,
                        'valor': ganhador['gb_valor'],
                        'milhar': ganhador['gb_bilhete_premiado'],
                        'data': datetime.fromisoformat(ganhador['gb_data_criacao']).strftime('%d/%m/%Y')
                    })
            except Exception as e:
                log_error("ultimos_ganhadores", e)
        else:
            # Buscar em memória
            ganhadores_ml = [g for g in memory_storage['ganhadores'] if g.get('tipo_jogo') == '2para1000']
            ganhadores_ordenados = sorted(
                ganhadores_ml, 
                key=lambda x: x.get('data_criacao', ''), 
                reverse=True
            )[:10]
            
            for ganhador in ganhadores_ordenados:
                nome_display = ganhador['nome']
                if len(nome_display) > 15:
                    nome_display = nome_display[:15] + '...'
                
                ganhadores.append({
                    'nome': nome_display,
                    'valor': ganhador['valor'],
                    'milhar': ganhador.get('bilhete_premiado', ''),
                    'data': datetime.fromisoformat(ganhador['data_criacao']).strftime('%d/%m/%Y')
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
        
        nome = data.get('nome', '').strip()
        telefone = data.get('telefone', '').strip()
        email = data.get('email', '').strip().lower()
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')

        log_info("cadastrar_afiliado", f"Tentativa de cadastro: {nome}, {email}, CPF: {cpf[:3]}***")

        # Validações mais flexíveis
        if not nome or len(nome) < 2:
            log_error("cadastrar_afiliado", "Nome inválido", {"nome": nome})
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 2 caracteres'})
        
        if not email or '@' not in email or len(email) < 5:
            log_error("cadastrar_afiliado", "Email inválido", {"email": email})
            return jsonify({'sucesso': False, 'erro': 'Email inválido'})
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            log_error("cadastrar_afiliado", "CPF inválido", {"cpf_length": len(cpf), "cpf": cpf[:3] + "***"})
            return jsonify({'sucesso': False, 'erro': 'CPF deve ter exatamente 11 números'})

        if not telefone or len(telefone) < 10:
            log_error("cadastrar_afiliado", "Telefone inválido", {"telefone": telefone})
            return jsonify({'sucesso': False, 'erro': 'Telefone deve ter pelo menos 10 dígitos'})

        codigo = gerar_codigo_afiliado()
        
        afiliado_data = {
            'codigo': codigo,
            'nome': nome[:255],
            'telefone': telefone[:20],
            'email': email[:255],
            'cpf': cpf,
            'status': 'ativo',
            'total_clicks': 0,
            'total_vendas': 0,
            'total_comissao': 0.0,
            'saldo_disponivel': 0.0,
            'data_cadastro': datetime.now().isoformat()
        }

        if supabase:
            try:
                # Verificar duplicatas com tratamento de erro melhorado
                try:
                    existing_email = supabase.table('gb_afiliados').select('gb_id').eq('gb_email', email).execute()
                    if existing_email.data and len(existing_email.data) > 0:
                        log_error("cadastrar_afiliado", "Email duplicado", {"email": email})
                        return jsonify({'sucesso': False, 'erro': 'Este email já está cadastrado'})
                except Exception as e:
                    log_error("cadastrar_afiliado", f"Erro ao verificar email: {str(e)}")

                try:
                    existing_cpf = supabase.table('gb_afiliados').select('gb_id').eq('gb_cpf', cpf).execute()
                    if existing_cpf.data and len(existing_cpf.data) > 0:
                        log_error("cadastrar_afiliado", "CPF duplicado", {"cpf": cpf[:3] + "***"})
                        return jsonify({'sucesso': False, 'erro': 'Este CPF já está cadastrado'})
                except Exception as e:
                    log_error("cadastrar_afiliado", f"Erro ao verificar CPF: {str(e)}")

                # Inserir novo afiliado
                response = supabase.table('gb_afiliados').insert({
                    'gb_codigo': codigo,
                    'gb_nome': nome[:255],
                    'gb_telefone': telefone[:20],
                    'gb_email': email[:255],
                    'gb_cpf': cpf,
                    'gb_status': 'ativo',
                    'gb_total_clicks': 0,
                    'gb_total_vendas': 0,
                    'gb_total_comissao': 0.0,
                    'gb_saldo_disponivel': 0.0
                }).execute()

                if response.data and len(response.data) > 0:
                    afiliado = response.data[0]
                    log_info("cadastrar_afiliado", f"Afiliado cadastrado com sucesso: {nome} - Código: {codigo}")
                    
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['gb_id'],
                            'codigo': codigo,
                            'nome': nome,
                            'email': email,
                            'telefone': telefone,
                            'total_clicks': 0,
                            'total_vendas': 0,
                            'total_comissao': 0,
                            'saldo_disponivel': 0
                        }
                    })
                else:
                    log_error("cadastrar_afiliado", "Erro na inserção - resposta vazia")
                    return jsonify({'sucesso': False, 'erro': 'Erro ao salvar dados no banco'})
                    
            except Exception as e:
                log_error("cadastrar_afiliado", f"Erro no Supabase: {str(e)}")
                return jsonify({'sucesso': False, 'erro': 'Erro interno do banco de dados'})
        else:
            # Verificar duplicatas em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('email') == email:
                    return jsonify({'sucesso': False, 'erro': 'Este email já está cadastrado'})
                if afiliado.get('cpf') == cpf:
                    return jsonify({'sucesso': False, 'erro': 'Este CPF já está cadastrado'})
            
            afiliado_data['id'] = len(memory_storage['afiliados']) + 1
            memory_storage['afiliados'].append(afiliado_data)
            
            log_info("cadastrar_afiliado", f"Afiliado cadastrado em memória: {nome} - Código: {codigo}")
            
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'id': afiliado_data['id'],
                    'codigo': codigo,
                    'nome': nome,
                    'email': email,
                    'telefone': telefone,
                    'total_clicks': 0,
                    'total_vendas': 0,
                    'total_comissao': 0,
                    'saldo_disponivel': 0
                }
            })

    except Exception as e:
        log_error("cadastrar_afiliado", f"Erro geral: {str(e)}")
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
                response = supabase.table('gb_afiliados').select('*').eq('gb_cpf', cpf).eq('gb_status', 'ativo').execute()
                
                if response.data:
                    afiliado = response.data[0]
                    
                    log_info("login_afiliado", f"Afiliado logado: {afiliado['gb_nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['gb_id'],
                            'codigo': afiliado['gb_codigo'],
                            'nome': afiliado['gb_nome'],
                            'email': afiliado['gb_email'],
                            'telefone': afiliado['gb_telefone'],
                            'total_clicks': afiliado.get('gb_total_clicks', 0),
                            'total_vendas': afiliado.get('gb_total_vendas', 0),
                            'total_comissao': afiliado.get('gb_total_comissao', 0),
                            'saldo_disponivel': afiliado.get('gb_saldo_disponivel', 0),
                            'chave_pix': afiliado.get('gb_chave_pix'),
                            'tipo_chave_pix': afiliado.get('gb_tipo_chave_pix')
                        }
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
                    
            except Exception as e:
                log_error("login_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Buscar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('cpf') == cpf and afiliado.get('status') == 'ativo':
                    log_info("login_afiliado", f"Afiliado logado em memória: {afiliado['nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'afiliado': {
                            'id': afiliado['id'],
                            'codigo': afiliado['codigo'],
                            'nome': afiliado['nome'],
                            'email': afiliado['email'],
                            'telefone': afiliado['telefone'],
                            'total_clicks': afiliado.get('total_clicks', 0),
                            'total_vendas': afiliado.get('total_vendas', 0),
                            'total_comissao': afiliado.get('total_comissao', 0),
                            'saldo_disponivel': afiliado.get('saldo_disponivel', 0),
                            'chave_pix': afiliado.get('chave_pix'),
                            'tipo_chave_pix': afiliado.get('tipo_chave_pix')
                        }
                    })
            
            return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
            
    except Exception as e:
        log_error("login_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/click_afiliado', methods=['POST'])
def click_afiliado():
    """Registra clique do afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código do afiliado é obrigatório'})
        
        if supabase:
            try:
                # Buscar afiliado
                afiliado = supabase.table('gb_afiliados').select('*').eq('gb_codigo', codigo).eq('gb_status', 'ativo').execute()
                
                if afiliado.data:
                    afiliado_id = afiliado.data[0]['gb_id']
                    
                    # Registrar clique
                    supabase.table('gb_afiliado_clicks').insert({
                        'gb_afiliado_id': afiliado_id,
                        'gb_ip_visitor': request.remote_addr or 'unknown',
                        'gb_user_agent': request.headers.get('User-Agent', '')[:500],
                        'gb_referrer': request.headers.get('Referer', '')[:500]
                    }).execute()
                    
                    # Incrementar contador
                    current_clicks = afiliado.data[0].get('gb_total_clicks', 0) or 0
                    supabase.table('gb_afiliados').update({
                        'gb_total_clicks': current_clicks + 1
                    }).eq('gb_id', afiliado_id).execute()
                    
                    log_info("click_afiliado", f"Clique registrado para afiliado: {codigo}")
                    return jsonify({'sucesso': True})
                    
            except Exception as e:
                log_error("click_afiliado", e)
        else:
            # Registrar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('codigo') == codigo and afiliado.get('status') == 'ativo':
                    afiliado['total_clicks'] = afiliado.get('total_clicks', 0) + 1
                    
                    memory_storage['afiliado_clicks'].append({
                        'id': len(memory_storage['afiliado_clicks']) + 1,
                        'afiliado_id': afiliado['id'],
                        'ip_visitor': request.remote_addr or 'unknown',
                        'user_agent': request.headers.get('User-Agent', '')[:500],
                        'referrer': request.headers.get('Referer', '')[:500],
                        'data_click': datetime.now().isoformat()
                    })
                    
                    log_info("click_afiliado", f"Clique registrado em memória para afiliado: {codigo}")
                    return jsonify({'sucesso': True})
        
        return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
        
    except Exception as e:
        log_error("click_afiliado", e)
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
                response = supabase.table('gb_afiliados').update({
                    'gb_chave_pix': chave_pix[:255],
                    'gb_tipo_chave_pix': tipo_chave
                }).eq('gb_codigo', codigo).eq('gb_status', 'ativo').execute()
                
                if response.data:
                    log_info("atualizar_pix_afiliado", f"PIX atualizado para afiliado: {codigo}")
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
                    afiliado['chave_pix'] = chave_pix[:255]
                    afiliado['tipo_chave_pix'] = tipo_chave
                    
                    log_info("atualizar_pix_afiliado", f"PIX atualizado em memória para afiliado: {codigo}")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
        
    except Exception as e:
        log_error("atualizar_pix_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/solicitar_saque_afiliado', methods=['POST'])
def solicitar_saque_afiliado():
    """Solicita saque do afiliado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código do afiliado é obrigatório'})
        
        if supabase:
            try:
                # Buscar afiliado
                afiliado = supabase.table('gb_afiliados').select('*').eq('gb_codigo', codigo).eq('gb_status', 'ativo').execute()
                
                if not afiliado.data:
                    return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
                
                afiliado_data = afiliado.data[0]
                saldo = afiliado_data.get('gb_saldo_disponivel', 0) or 0
                
                if saldo < 10:
                    return jsonify({'sucesso': False, 'erro': 'Saldo mínimo para saque: R$ 10,00'})
                
                if not afiliado_data.get('gb_chave_pix'):
                    return jsonify({'sucesso': False, 'erro': 'Configure sua chave PIX primeiro'})
                
                # Criar solicitação de saque
                supabase.table('gb_saques').insert({
                    'gb_afiliado_id': afiliado_data['gb_id'],
                    'gb_valor': saldo,
                    'gb_chave_pix': afiliado_data['gb_chave_pix'],
                    'gb_tipo_chave': afiliado_data.get('gb_tipo_chave_pix', 'cpf'),
                    'gb_status': 'solicitado'
                }).execute()
                
                # Zerar saldo do afiliado
                supabase.table('gb_afiliados').update({
                    'gb_saldo_disponivel': 0
                }).eq('gb_id', afiliado_data['gb_id']).execute()
                
                log_info("solicitar_saque_afiliado", f"Saque solicitado: {codigo} - R$ {saldo:.2f}")
                return jsonify({
                    'sucesso': True,
                    'valor': saldo
                })
                
            except Exception as e:
                log_error("solicitar_saque_afiliado", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Processar em memória
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('codigo') == codigo and afiliado.get('status') == 'ativo':
                    saldo = afiliado.get('saldo_disponivel', 0)
                    
                    if saldo < 10:
                        return jsonify({'sucesso': False, 'erro': 'Saldo mínimo para saque: R$ 10,00'})
                    
                    if not afiliado.get('chave_pix'):
                        return jsonify({'sucesso': False, 'erro': 'Configure sua chave PIX primeiro'})
                    
                    # Criar solicitação
                    memory_storage['saques'].append({
                        'id': len(memory_storage['saques']) + 1,
                        'afiliado_id': afiliado['id'],
                        'afiliado_nome': afiliado['nome'],
                        'afiliado_codigo': codigo,
                        'valor': saldo,
                        'chave_pix': afiliado['chave_pix'],
                        'tipo_chave': afiliado.get('tipo_chave_pix', 'cpf'),
                        'status': 'solicitado',
                        'data_solicitacao': datetime.now().isoformat()
                    })
                    
                    # Zerar saldo
                    afiliado['saldo_disponivel'] = 0
                    
                    log_info("solicitar_saque_afiliado", f"Saque solicitado em memória: {codigo} - R$ {saldo:.2f}")
                    return jsonify({
                        'sucesso': True,
                        'valor': saldo
                    })
            
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
        
    except Exception as e:
        log_error("solicitar_saque_afiliado", e)
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
        hoje = date.today().isoformat()
        
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
            'sistema_ativo': obter_configuracao('sistema_ativo', 'true').lower() == 'true',
            'total_clientes': 0
        }
        
        if supabase:
            try:
                # Total de clientes
                clientes = supabase.table('gb_clientes').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['total_clientes'] = len(clientes.data or [])
                
                if game in ['raspa_brasil', 'both']:
                    vendidas_rb = obter_total_vendas('raspa_brasil')
                    stats['vendidas'] = vendidas_rb
                    stats['restantes'] = TOTAL_RASPADINHAS - vendidas_rb
                    
                    ganhadores_rb = supabase.table('gb_ganhadores').select('gb_id').eq('gb_tipo_jogo', 'raspa_brasil').execute()
                    stats['ganhadores'] = len(ganhadores_rb.data or [])
                    
                    # Vendas de hoje RB
                    vendas_hoje_rb = supabase.table('gb_vendas').select('gb_quantidade').gte(
                        'gb_data_criacao', hoje + ' 00:00:00'
                    ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', 'raspa_brasil').eq('gb_status', 'completed').execute()
                    stats['vendas_hoje'] = sum(v['gb_quantidade'] for v in (vendas_hoje_rb.data or []))
                
                if game in ['2para1000', 'both']:
                    vendidos_ml = obter_total_vendas('2para1000')
                    stats['bilhetes_vendidos'] = vendidos_ml
                    
                    ganhadores_ml = supabase.table('gb_ganhadores').select('gb_id').eq('gb_tipo_jogo', '2para1000').execute()
                    stats['total_ganhadores'] = len(ganhadores_ml.data or [])
                    
                    # Vendas de hoje ML
                    vendas_hoje_ml = supabase.table('gb_vendas').select('gb_quantidade').gte(
                        'gb_data_criacao', hoje + ' 00:00:00'
                    ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', '2para1000').eq('gb_status', 'completed').execute()
                    stats['vendas_hoje_ml'] = sum(v['gb_quantidade'] for v in (vendas_hoje_ml.data or []))
                
                # Afiliados
                afiliados = supabase.table('gb_afiliados').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['afiliados'] = len(afiliados.data or [])
                
            except Exception as e:
                log_error("admin_stats", e)
        else:
            # Estatísticas da memória
            stats['total_clientes'] = len([c for c in memory_storage['clientes'] if c.get('status') == 'ativo'])
            stats['ganhadores'] = len([g for g in memory_storage['ganhadores'] if g.get('tipo_jogo') == 'raspa_brasil'])
            stats['total_ganhadores'] = len([g for g in memory_storage['ganhadores'] if g.get('tipo_jogo') == '2para1000'])
            stats['afiliados'] = len([a for a in memory_storage['afiliados'] if a.get('status') == 'ativo'])
            stats['vendas_hoje'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == 'raspa_brasil' and v.get('status') == 'completed'])
            stats['vendas_hoje_ml'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == '2para1000' and v.get('status') == 'completed'])

        log_info("admin_stats", f"Stats consultadas - Game: {game}")
        return jsonify(stats)

    except Exception as e:
        log_error("admin_stats", e)
        return jsonify(stats)

@app.route('/admin/verificar_status_premio')
def admin_verificar_status_premio():
    """Verifica status do prêmio manual do Raspa Brasil"""
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
        return jsonify({'premio_liberado': False, 'valor': None})

@app.route('/admin/liberar_premio_manual', methods=['POST'])
def admin_liberar_premio_manual():
    """Libera prêmio manual para o Raspa Brasil"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        valor = data.get('valor', '').strip()
        
        if not valor:
            return jsonify({'sucesso': False, 'erro': 'Valor é obrigatório'})
        
        # Verificar se já há prêmio liberado
        premio_atual = obter_configuracao('premio_manual_liberado', '')
        if premio_atual:
            return jsonify({'sucesso': False, 'erro': 'Já existe um prêmio liberado. Aguarde ser raspado.'})
        
        if atualizar_configuracao('premio_manual_liberado', valor, 'raspa_brasil'):
            log_info("admin_liberar_premio_manual", f"Prêmio {valor} liberado pelo admin")
            return jsonify({'sucesso': True, 'valor': valor})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar configuração'})
        
    except Exception as e:
        log_error("admin_liberar_premio_manual", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/editar_premio_ml', methods=['POST'])
def admin_editar_premio_ml():
    """Edita o valor do prêmio acumulado do 2 para 1000"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        novo_valor = data.get('valor')
        
        if not novo_valor:
            return jsonify({'sucesso': False, 'erro': 'Valor é obrigatório'})
        
        try:
            valor_float = float(str(novo_valor).replace(',', '.'))
            if valor_float < 0:
                return jsonify({'sucesso': False, 'erro': 'Valor não pode ser negativo'})
        except:
            return jsonify({'sucesso': False, 'erro': 'Valor inválido'})
        
        if atualizar_configuracao('premio_acumulado', str(valor_float), '2para1000'):
            log_info("admin_editar_premio_ml", f"Prêmio ML alterado para: R$ {valor_float:.2f}")
            return jsonify({
                'sucesso': True,
                'novo_valor': f"R$ {valor_float:.2f}".replace('.', ',')
            })
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar configuração'})
        
    except Exception as e:
        log_error("admin_editar_premio_ml", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/sortear', methods=['POST'])
def admin_sortear():
    """Realiza sorteio do 2 para 1000 - CORRIGIDO para estrutura atual"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        milhar_sorteada = data.get('milhar_sorteada', '').strip()
        
        if not milhar_sorteada or len(milhar_sorteada) != 4 or not milhar_sorteada.isdigit():
            return jsonify({'sucesso': False, 'erro': 'Digite exatamente 4 números'})
        
        hoje = date.today().isoformat()
        
        # Verificar se já foi sorteado hoje
        if supabase:
            try:
                existing = supabase.table('gb_sorteios').select('gb_id').eq('gb_data_sorteio', hoje).execute()
                if existing.data:
                    return jsonify({'sucesso': False, 'erro': 'Sorteio já realizado hoje'})
            except Exception as e:
                log_error("admin_sortear_check", e)
        else:
            for sorteio in memory_storage['sorteios']:
                if sorteio.get('data_sorteio') == hoje:
                    return jsonify({'sucesso': False, 'erro': 'Sorteio já realizado hoje'})
        
        # Buscar bilhetes participantes
        ganhador = None
        participantes = []
        
        if supabase:
            try:
                bilhetes = supabase.table('gb_cliente_bilhetes').select('*').eq(
                    'gb_data_sorteio', hoje
                ).eq('gb_status', 'ativo').execute()
                
                for bilhete in (bilhetes.data or []):
                    participantes.append(bilhete)
                    if bilhete['gb_numero_bilhete'] == milhar_sorteada:
                        # Buscar dados do cliente
                        cliente = supabase.table('gb_clientes').select('*').eq('gb_id', bilhete['gb_cliente_id']).execute()
                        if cliente.data:
                            ganhador = {
                                'nome': cliente.data[0]['gb_nome'],
                                'bilhete': milhar_sorteada,
                                'cliente_id': bilhete['gb_cliente_id']
                            }
                        break
            except Exception as e:
                log_error("admin_sortear_bilhetes", e)
        else:
            for bilhete in memory_storage['cliente_bilhetes']:
                if bilhete.get('data_sorteio') == hoje and bilhete.get('status') == 'ativo':
                    participantes.append(bilhete)
                    if bilhete['numero_bilhete'] == milhar_sorteada:
                        # Buscar cliente
                        for cliente in memory_storage['clientes']:
                            if cliente.get('id') == bilhete['cliente_id']:
                                ganhador = {
                                    'nome': cliente['nome'],
                                    'bilhete': milhar_sorteada,
                                    'cliente_id': bilhete['cliente_id']
                                }
                                break
                        break
        
        valor_atual = obter_premio_acumulado()
        houve_ganhador = ganhador is not None
        
        if houve_ganhador:
            # Registrar ganhador
            if supabase:
                try:
                    # Buscar dados do cliente para PIX
                    cliente_data = supabase.table('gb_clientes').select('*').eq('gb_id', ganhador['cliente_id']).execute()
                    chave_pix = cliente_data.data[0].get('gb_chave_pix', '') if cliente_data.data else ''
                    
                    supabase.table('gb_ganhadores').insert({
                        'gb_cliente_id': ganhador['cliente_id'],
                        'gb_tipo_jogo': '2para1000',
                        'gb_nome': ganhador['nome'],
                        'gb_valor': f"R$ {valor_atual:.2f}".replace('.', ','),
                        'gb_bilhete_premiado': milhar_sorteada,
                        'gb_chave_pix': chave_pix,
                        'gb_status_pagamento': 'pendente'
                    }).execute()
                    
                    # Marcar bilhete como premiado
                    supabase.table('gb_cliente_bilhetes').update({
                        'gb_status': 'premiado',
                        'gb_premio_ganho': valor_atual
                    }).eq('gb_numero_bilhete', milhar_sorteada).eq('gb_data_sorteio', hoje).execute()
                    
                except Exception as e:
                    log_error("admin_sortear_ganhador", e)
            else:
                # Registrar em memória
                memory_storage['ganhadores'].append({
                    'id': len(memory_storage['ganhadores']) + 1,
                    'cliente_id': ganhador['cliente_id'],
                    'tipo_jogo': '2para1000',
                    'nome': ganhador['nome'],
                    'valor': f"R$ {valor_atual:.2f}".replace('.', ','),
                    'bilhete_premiado': milhar_sorteada,
                    'chave_pix': '',
                    'status_pagamento': 'pendente',
                    'data_criacao': datetime.now().isoformat()
                })
                
                # Marcar bilhete como premiado
                for bilhete in memory_storage['cliente_bilhetes']:
                    if bilhete.get('numero_bilhete') == milhar_sorteada and bilhete.get('data_sorteio') == hoje:
                        bilhete['status'] = 'premiado'
                        bilhete['premio_ganho'] = valor_atual
                        break
            
            # Resetar prêmio para valor inicial
            novo_valor_acumulado = PREMIO_INICIAL_ML
        else:
            # Acumular R$ 1000
            novo_valor_acumulado = valor_atual + 1000.0
        
        # Atualizar prêmio acumulado
        atualizar_configuracao('premio_acumulado', str(novo_valor_acumulado), '2para1000')
        
        # Registrar sorteio - AJUSTADO PARA ESTRUTURA ATUAL
        if supabase:
            try:
                # Preparar dados extras
                bilhetes_ganhadores = milhar_sorteada if houve_ganhador else None
                observacoes = f"Ganhador: {ganhador['nome']}" if ganhador else "Sem ganhador - prêmio acumulado"
                
                supabase.table('gb_sorteios').insert({
                    'gb_data_sorteio': hoje,
                    'gb_milhar_sorteada': milhar_sorteada,
                    'gb_houve_ganhador': houve_ganhador,
                    'gb_ganhador_nome': ganhador['nome'] if ganhador else None,
                    'gb_valor_premio': valor_atual if houve_ganhador else None,
                    'gb_novo_valor_acumulado': novo_valor_acumulado,
                    'gb_total_participantes': len(participantes),
                    'gb_bilhetes_ganhadores': bilhetes_ganhadores,
                    'gb_observacoes': observacoes
                }).execute()
            except Exception as e:
                log_error("admin_sortear_save", e)
        else:
            memory_storage['sorteios'].append({
                'id': len(memory_storage['sorteios']) + 1,
                'data_sorteio': hoje,
                'milhar_sorteada': milhar_sorteada,
                'houve_ganhador': houve_ganhador,
                'ganhador_nome': ganhador['nome'] if ganhador else None,
                'valor_premio': valor_atual if houve_ganhador else None,
                'novo_valor_acumulado': novo_valor_acumulado,
                'total_participantes': len(participantes),
                'bilhetes_ganhadores': bilhetes_ganhadores if houve_ganhador else None,
                'observacoes': f"Ganhador: {ganhador['nome']}" if ganhador else "Sem ganhador",
                'data_criacao': datetime.now().isoformat()
            })
        
        log_info("admin_sortear", f"Sorteio realizado: {milhar_sorteada} - Ganhador: {houve_ganhador} - Novo valor: {novo_valor_acumulado}")
        
        response_data = {
            'sucesso': True,
            'houve_ganhador': houve_ganhador,
            'novo_valor_acumulado': f"{novo_valor_acumulado:.2f}".replace('.', ','),
            'milhar_sorteada': milhar_sorteada  # IMPORTANTE: retornar o número sorteado
        }
        
        if houve_ganhador:
            response_data.update({
                'ganhador': ganhador,
                'valor_premio': f"{valor_atual:.2f}".replace('.', ',')
            })
        
        return jsonify(response_data)
        
    except Exception as e:
        log_error("admin_sortear", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})


@app.route('/admin/afiliados')
def admin_afiliados():
    """Obtém lista de afiliados para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        afiliados = []
        
        if supabase:
            try:
                response = supabase.table('gb_afiliados').select('*').order('gb_data_criacao', desc=True).execute()
                
                for a in (response.data or []):
                    afiliados.append({
                        'id': a['gb_id'],
                        'codigo': a['gb_codigo'],
                        'nome': a['gb_nome'],
                        'email': a['gb_email'],
                        'telefone': a['gb_telefone'],
                        'status': a['gb_status'],
                        'total_clicks': a.get('gb_total_clicks', 0),
                        'total_vendas': a.get('gb_total_vendas', 0),
                        'total_comissao': a.get('gb_total_comissao', 0),
                        'saldo_disponivel': a.get('gb_saldo_disponivel', 0),
                        'chave_pix': a.get('gb_chave_pix', ''),
                        'tipo_chave_pix': a.get('gb_tipo_chave_pix', ''),
                        'data_cadastro': a['gb_data_criacao']
                    })
                    
            except Exception as e:
                log_error("admin_afiliados", e)
        else:
            # Buscar em memória
            for a in memory_storage['afiliados']:
                afiliados.append({
                    'id': a['id'],
                    'codigo': a['codigo'],
                    'nome': a['nome'],
                    'email': a['email'],
                    'telefone': a['telefone'],
                    'status': a['status'],
                    'total_clicks': a.get('total_clicks', 0),
                    'total_vendas': a.get('total_vendas', 0),
                    'total_comissao': a.get('total_comissao', 0),
                    'saldo_disponivel': a.get('saldo_disponivel', 0),
                    'chave_pix': a.get('chave_pix', ''),
                    'tipo_chave_pix': a.get('tipo_chave_pix', ''),
                    'data_cadastro': a['data_cadastro']
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
                query = supabase.table('gb_saques').select('*').order('gb_data_criacao', desc=True)
                
                if status != 'todos':
                    if status == 'pendente':
                        query = query.eq('gb_status', 'solicitado')
                    else:
                        query = query.eq('gb_status', status)
                
                response = query.execute()
                
                for s in (response.data or []):
                    # Buscar nome do afiliado
                    afiliado = supabase.table('gb_afiliados').select('gb_nome, gb_codigo').eq('gb_id', s.get('gb_afiliado_id')).execute()
                    afiliado_nome = afiliado.data[0]['gb_nome'] if afiliado.data else 'Desconhecido'
                    afiliado_codigo = afiliado.data[0]['gb_codigo'] if afiliado.data else ''
                    
                    saques.append({
                        'id': s['gb_id'],
                        'valor': s['gb_valor'],
                        'chave_pix': s['gb_chave_pix'],
                        'tipo_chave': s['gb_tipo_chave'],
                        'status': s['gb_status'],
                        'data_solicitacao': s['gb_data_criacao'],
                        'afiliado_nome': afiliado_nome,
                        'afiliado_codigo': afiliado_codigo
                    })
                    
            except Exception as e:
                log_error("admin_saques", e)
        else:
            # Buscar em memória
            filtro_status = 'solicitado' if status == 'pendente' else status
            
            for s in memory_storage['saques']:
                if status == 'todos' or s.get('status') == filtro_status:
                    saques.append({
                        'id': s['id'],
                        'valor': s['valor'],
                        'chave_pix': s['chave_pix'],
                        'tipo_chave': s['tipo_chave'],
                        'status': s['status'],
                        'data_solicitacao': s['data_solicitacao'],
                        'afiliado_nome': s['afiliado_nome'],
                        'afiliado_codigo': s['afiliado_codigo']
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
                response = supabase.table('gb_saques').update({
                    'gb_status': 'pago',
                    'gb_data_pagamento': datetime.now().isoformat()
                }).eq('gb_id', saque_id).execute()
                
                if response.data:
                    log_info("admin_marcar_saque_pago", f"Saque {saque_id} marcado como pago")
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
                    
                    log_info("admin_marcar_saque_pago", f"Saque {saque_id} marcado como pago em memória")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Saque não encontrado'})
        
    except Exception as e:
        log_error("admin_marcar_saque_pago", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/bilhetes/<data_filtro>')
def admin_bilhetes(data_filtro):
    """Obtém bilhetes vendidos para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        bilhetes = []
        
        if supabase:
            try:
                # Buscar vendas do dia
                vendas = supabase.table('gb_vendas').select('*').gte(
                    'gb_data_criacao', data_filtro + ' 00:00:00'
                ).lt('gb_data_criacao', data_filtro + ' 23:59:59').eq(
                    'gb_tipo_jogo', '2para1000'
                ).eq('gb_status', 'completed').execute()
                
                for venda in (vendas.data or []):
                    # Buscar bilhetes da venda
                    bilhetes_venda = supabase.table('gb_cliente_bilhetes').select('gb_numero_bilhete').eq(
                        'gb_venda_id', venda['gb_id']
                    ).execute()
                    
                    numeros_bilhetes = [b['gb_numero_bilhete'] for b in (bilhetes_venda.data or [])]
                    
                    # Buscar dados do cliente
                    cliente = supabase.table('gb_clientes').select('gb_nome, gb_telefone, gb_chave_pix').eq(
                        'gb_id', venda['gb_cliente_id']
                    ).execute()
                    
                    cliente_data = cliente.data[0] if cliente.data else {}
                    
                    bilhetes.append({
                        'payment_id': venda['gb_payment_id'],
                        'nome': cliente_data.get('gb_nome', 'N/A'),
                        'telefone': cliente_data.get('gb_telefone', 'N/A'),
                        'chave_pix': cliente_data.get('gb_chave_pix', 'N/A'),
                        'bilhetes': numeros_bilhetes,
                        'data_sorteio': data_filtro
                    })
                    
            except Exception as e:
                log_error("admin_bilhetes", e)
        else:
            # Buscar em memória
            for venda in memory_storage['vendas']:
                if (venda.get('data_criacao', '')[:10] == data_filtro and 
                    venda.get('tipo_jogo') == '2para1000' and 
                    venda.get('status') == 'completed'):
                    
                    # Buscar bilhetes
                    numeros_bilhetes = []
                    for bilhete in memory_storage['cliente_bilhetes']:
                        if bilhete.get('venda_id') == venda['id']:
                            numeros_bilhetes.append(bilhete['numero_bilhete'])
                    
                    # Buscar cliente
                    cliente_data = {}
                    for cliente in memory_storage['clientes']:
                        if cliente.get('id') == venda['cliente_id']:
                            cliente_data = cliente
                            break
                    
                    bilhetes.append({
                        'payment_id': venda['payment_id'],
                        'nome': cliente_data.get('nome', 'N/A'),
                        'telefone': cliente_data.get('telefone', 'N/A'),
                        'chave_pix': cliente_data.get('chave_pix', 'N/A'),
                        'bilhetes': numeros_bilhetes,
                        'data_sorteio': data_filtro
                    })
        
        log_info("admin_bilhetes", f"Bilhetes consultados - Data: {data_filtro}, Total: {len(bilhetes)}")
        return jsonify({'bilhetes': bilhetes})
        
    except Exception as e:
        log_error("admin_bilhetes", e)
        return jsonify({'bilhetes': []})

@app.route('/admin/raspadinhas/<data_filtro>')
def admin_raspadinhas(data_filtro):
    """Obtém raspadinhas vendidas para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        vendas = []
        estatisticas = {
            'total_vendidas': 0,
            'total_usadas': 0,
            'total_pendentes': 0
        }
        
        if supabase:
            try:
                # Buscar vendas do dia
                vendas_response = supabase.table('gb_vendas').select('*').gte(
                    'gb_data_criacao', data_filtro + ' 00:00:00'
                ).lt('gb_data_criacao', data_filtro + ' 23:59:59').eq(
                    'gb_tipo_jogo', 'raspa_brasil'
                ).order('gb_data_criacao', desc=True).execute()
                
                for venda in (vendas_response.data or []):
                    # Buscar dados do afiliado se houver
                    afiliado_nome = ''
                    if venda.get('gb_afiliado_id'):
                        afiliado = supabase.table('gb_afiliados').select('gb_nome').eq(
                            'gb_id', venda['gb_afiliado_id']
                        ).execute()
                        if afiliado.data:
                            afiliado_nome = afiliado.data[0]['gb_nome']
                    
                    raspadinhas_usadas = venda.get('gb_raspadinhas_usadas', 0) or 0
                    
                    vendas.append({
                        'payment_id': venda['gb_payment_id'],
                        'quantidade': venda['gb_quantidade'],
                        'valor_total': venda['gb_valor_total'],
                        'status': venda['gb_status'],
                        'ip_cliente': venda['gb_ip_cliente'],
                        'raspadinhas_usadas': raspadinhas_usadas,
                        'afiliado_nome': afiliado_nome,
                        'data_criacao': venda['gb_data_criacao']
                    })
                    
                    # Atualizar estatísticas
                    if venda['gb_status'] == 'completed':
                        estatisticas['total_vendidas'] += venda['gb_quantidade']
                        estatisticas['total_usadas'] += raspadinhas_usadas
                        estatisticas['total_pendentes'] += (venda['gb_quantidade'] - raspadinhas_usadas)
                    
            except Exception as e:
                log_error("admin_raspadinhas", e)
        else:
            # Buscar em memória
            for venda in memory_storage['vendas']:
                if (venda.get('data_criacao', '')[:10] == data_filtro and 
                    venda.get('tipo_jogo') == 'raspa_brasil'):
                    
                    # Buscar afiliado
                    afiliado_nome = ''
                    if venda.get('afiliado_id'):
                        for afiliado in memory_storage['afiliados']:
                            if afiliado.get('id') == venda['afiliado_id']:
                                afiliado_nome = afiliado['nome']
                                break
                    
                    raspadinhas_usadas = venda.get('raspadinhas_usadas', 0)
                    
                    vendas.append({
                        'payment_id': venda['payment_id'],
                        'quantidade': venda['quantidade'],
                        'valor_total': venda['valor_total'],
                        'status': venda['status'],
                        'ip_cliente': venda['ip_cliente'],
                        'raspadinhas_usadas': raspadinhas_usadas,
                        'afiliado_nome': afiliado_nome,
                        'data_criacao': venda['data_criacao']
                    })
                    
                    # Atualizar estatísticas
                    if venda['status'] == 'completed':
                        estatisticas['total_vendidas'] += venda['quantidade']
                        estatisticas['total_usadas'] += raspadinhas_usadas
                        estatisticas['total_pendentes'] += (venda['quantidade'] - raspadinhas_usadas)
        
        log_info("admin_raspadinhas", f"Raspadinhas consultadas - Data: {data_filtro}, Total: {len(vendas)}")
        return jsonify({
            'vendas': vendas,
            'estatisticas': estatisticas
        })
        
    except Exception as e:
        log_error("admin_raspadinhas", e)
        return jsonify({'vendas': [], 'estatisticas': estatisticas})

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
                query = supabase.table('gb_ganhadores').select('*').order('gb_data_criacao', desc=True)
                
                if game == 'raspa_brasil':
                    query = query.eq('gb_tipo_jogo', 'raspa_brasil')
                elif game == '2para1000':
                    query = query.eq('gb_tipo_jogo', '2para1000')
                
                if data_filtro:
                    query = query.gte('gb_data_criacao', data_filtro + ' 00:00:00').lt('gb_data_criacao', data_filtro + ' 23:59:59')
                
                response = query.limit(100).execute()
                
                for g in (response.data or []):
                    ganhador_data = {
                        'id': g['gb_id'],
                        'nome': g['gb_nome'],
                        'valor': g['gb_valor'],
                        'data': g['gb_data_criacao'],
                        'data_premio': g['gb_data_criacao'],
                        'status': g['gb_status_pagamento'],
                        'jogo': 'Raspa Brasil' if g['gb_tipo_jogo'] == 'raspa_brasil' else '2 para 1000',
                        'chave_pix': g.get('gb_chave_pix', '')
                    }
                    
                    if g['gb_tipo_jogo'] == 'raspa_brasil':
                        ganhador_data['codigo'] = g.get('gb_codigo_premio', '')
                    else:
                        ganhador_data['milhar'] = g.get('gb_bilhete_premiado', '')
                    
                    ganhadores.append(ganhador_data)
                    
            except Exception as e:
                log_error("admin_ganhadores", e)
        else:
            # Buscar em memória
            for g in memory_storage['ganhadores']:
                if game != 'todos' and g.get('tipo_jogo') != game:
                    continue
                    
                if data_filtro and g.get('data_criacao', '')[:10] != data_filtro:
                    continue
                
                ganhador_data = {
                    'id': g['id'],
                    'nome': g['nome'],
                    'valor': g['valor'],
                    'data': g['data_criacao'],
                    'data_premio': g['data_criacao'],
                    'status': g['status_pagamento'],
                    'jogo': 'Raspa Brasil' if g['tipo_jogo'] == 'raspa_brasil' else '2 para 1000',
                    'chave_pix': g.get('chave_pix', '')
                }
                
                if g['tipo_jogo'] == 'raspa_brasil':
                    ganhador_data['codigo'] = g.get('codigo', '')
                else:
                    ganhador_data['milhar'] = g.get('bilhete_premiado', '')
                
                ganhadores.append(ganhador_data)
        
        # Ordenar por data
        ganhadores.sort(key=lambda x: x['data'], reverse=True)
        
        log_info("admin_ganhadores", f"Ganhadores consultados - Game: {game}, Total: {len(ganhadores[:100])}")
        return jsonify({'ganhadores': ganhadores[:100]})
        
    except Exception as e:
        log_error("admin_ganhadores", e)
        return jsonify({'ganhadores': []})

@app.route('/admin/marcar_ganhador_pago', methods=['POST'])
def admin_marcar_ganhador_pago():
    """Marca ganhador como pago"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        ganhador_id = data.get('ganhador_id')
        
        if not ganhador_id:
            return jsonify({'sucesso': False, 'erro': 'ID do ganhador é obrigatório'})
        
        if supabase:
            try:
                response = supabase.table('gb_ganhadores').update({
                    'gb_status_pagamento': 'pago',
                    'gb_data_pagamento': datetime.now().isoformat()
                }).eq('gb_id', ganhador_id).execute()
                
                if response.data:
                    log_info("admin_marcar_ganhador_pago", f"Ganhador {ganhador_id} marcado como pago")
                    return jsonify({'sucesso': True})
                else:
                    return jsonify({'sucesso': False, 'erro': 'Ganhador não encontrado'})
                    
            except Exception as e:
                log_error("admin_marcar_ganhador_pago", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Atualizar em memória
            for ganhador in memory_storage['ganhadores']:
                if ganhador.get('id') == int(ganhador_id):
                    ganhador['status_pagamento'] = 'pago'
                    ganhador['data_pagamento'] = datetime.now().isoformat()
                    
                    log_info("admin_marcar_ganhador_pago", f"Ganhador {ganhador_id} marcado como pago em memória")
                    return jsonify({'sucesso': True})
            
            return jsonify({'sucesso': False, 'erro': 'Ganhador não encontrado'})
        
    except Exception as e:
        log_error("admin_marcar_ganhador_pago", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/adicionar_ganhador', methods=['POST'])
def admin_adicionar_ganhador():
    """Adiciona ganhador manual - CORRIGIDO para 2para1000"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        data = sanitizar_dados_entrada(request.json)
        
        jogo = data.get('jogo')
        nome = data.get('nome', '').strip()
        valor = data.get('valor', '').strip()
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')
        milhar = data.get('milhar', '').strip() if jogo == '2para1000' else None
        
        log_info("admin_adicionar_ganhador", f"Tentativa: Jogo={jogo}, Nome={nome}, Valor={valor}, Milhar={milhar}")
        
        # Validações
        if not all([jogo, nome, valor, chave_pix]):
            return jsonify({'sucesso': False, 'erro': 'Todos os campos são obrigatórios'})
        
        if jogo not in ['raspa_brasil', '2para1000']:
            return jsonify({'sucesso': False, 'erro': 'Tipo de jogo inválido'})
        
        # VALIDAÇÃO ESPECÍFICA PARA 2PARA1000
        if jogo == '2para1000':
            if not milhar or len(milhar) != 4 or not milhar.isdigit():
                return jsonify({'sucesso': False, 'erro': 'Milhar deve ter exatamente 4 dígitos numéricos'})
            
            # Verificar se a milhar não está duplicada
            if supabase:
                try:
                    existing_milhar = supabase.table('gb_ganhadores').select('gb_id').eq('gb_bilhete_premiado', milhar).eq('gb_tipo_jogo', '2para1000').execute()
                    if existing_milhar.data:
                        return jsonify({'sucesso': False, 'erro': 'Esta milhar já foi utilizada por outro ganhador'})
                except Exception as e:
                    log_error("admin_adicionar_ganhador_check_milhar", e)
        
        # Gerar código para Raspa Brasil
        codigo = gerar_codigo_antifraude() if jogo == 'raspa_brasil' else None
        
        if supabase:
            try:
                # Preparar dados do banco - ESTRUTURA CORRIGIDA
                db_data = {
                    'gb_tipo_jogo': jogo,
                    'gb_nome': nome[:255],
                    'gb_valor': valor,
                    'gb_chave_pix': chave_pix[:255],
                    'gb_tipo_chave_pix': tipo_chave,
                    'gb_status_pagamento': 'pendente',
                    'gb_ip_cliente': 'admin_manual'
                }
                
                # Adicionar campos específicos por jogo
                if jogo == 'raspa_brasil':
                    db_data['gb_codigo_premio'] = codigo
                    log_info("admin_adicionar_ganhador", f"Adicionando Raspa Brasil - Código: {codigo}")
                else:  # 2para1000
                    db_data['gb_bilhete_premiado'] = milhar
                    log_info("admin_adicionar_ganhador", f"Adicionando 2para1000 - Milhar: {milhar}")
                
                # INSERIR NO BANCO
                response = supabase.table('gb_ganhadores').insert(db_data).execute()
                
                if response.data and len(response.data) > 0:
                    ganhador_id = response.data[0]['gb_id']
                    log_info("admin_adicionar_ganhador", f"✅ SUCESSO: Ganhador {jogo} adicionado - ID: {ganhador_id}, Nome: {nome}, Valor: {valor}")
                    
                    # Retornar dados completos
                    return jsonify({
                        'sucesso': True, 
                        'id': ganhador_id,
                        'dados': {
                            'jogo': jogo,
                            'nome': nome,
                            'valor': valor,
                            'milhar': milhar if jogo == '2para1000' else None,
                            'codigo': codigo if jogo == 'raspa_brasil' else None
                        }
                    })
                else:
                    log_error("admin_adicionar_ganhador", "Resposta vazia do Supabase")
                    return jsonify({'sucesso': False, 'erro': 'Erro: resposta vazia do banco de dados'})
                    
            except Exception as e:
                log_error("admin_adicionar_ganhador", f"Erro no Supabase: {str(e)}")
                return jsonify({'sucesso': False, 'erro': f'Erro no banco de dados: {str(e)}'})
        else:
            # Adicionar em memória
            ganhador_data = {
                'id': len(memory_storage['ganhadores']) + 1,
                'tipo_jogo': jogo,
                'nome': nome[:255],
                'valor': valor,
                'chave_pix': chave_pix[:255],
                'tipo_chave_pix': tipo_chave,
                'status_pagamento': 'pendente',
                'ip_cliente': 'admin_manual',
                'data_criacao': datetime.now().isoformat()
            }
            
            if jogo == 'raspa_brasil':
                ganhador_data['codigo'] = codigo
            else:
                ganhador_data['bilhete_premiado'] = milhar
            
            memory_storage['ganhadores'].append(ganhador_data)
            
            log_info("admin_adicionar_ganhador", f"Ganhador manual adicionado em memória: {nome} - {valor} - Jogo: {jogo}")
            return jsonify({'sucesso': True, 'id': ganhador_data['id']})
        
    except Exception as e:
        log_error("admin_adicionar_ganhador", f"Erro geral: {str(e)}")
        return jsonify({'sucesso': False, 'erro': f'Erro interno: {str(e)}'})

@app.route('/admin/relatorio_vendas')
def admin_relatorio_vendas():
    """Gera relatório de vendas"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        hoje = date.today()
        vendas_7_dias = []
        
        relatorio = {
            'vendas_rb': 0,
            'vendas_ml': 0,
            'receita_total': 0.0,
            'vendas_hoje': 0,
            'vendas_7_dias': []
        }
        
        if supabase:
            try:
                # Total vendas RB
                vendas_rb = supabase.table('gb_vendas').select('gb_quantidade').eq(
                    'gb_tipo_jogo', 'raspa_brasil'
                ).eq('gb_status', 'completed').execute()
                relatorio['vendas_rb'] = sum(v['gb_quantidade'] for v in (vendas_rb.data or []))
                
                # Total vendas ML
                vendas_ml = supabase.table('gb_vendas').select('gb_quantidade').eq(
                    'gb_tipo_jogo', '2para1000'
                ).eq('gb_status', 'completed').execute()
                relatorio['vendas_ml'] = sum(v['gb_quantidade'] for v in (vendas_ml.data or []))
                
                # Receita total
                vendas_todas = supabase.table('gb_vendas').select('gb_valor_total').eq('gb_status', 'completed').execute()
                relatorio['receita_total'] = sum(v['gb_valor_total'] for v in (vendas_todas.data or []))
                
                # Vendas de hoje
                hoje_str = hoje.isoformat()
                vendas_hoje = supabase.table('gb_vendas').select('gb_quantidade').gte(
                    'gb_data_criacao', hoje_str + ' 00:00:00'
                ).lt('gb_data_criacao', hoje_str + ' 23:59:59').eq('gb_status', 'completed').execute()
                relatorio['vendas_hoje'] = sum(v['gb_quantidade'] for v in (vendas_hoje.data or []))
                
                # Vendas dos últimos 7 dias
                for i in range(7):
                    dia = hoje - timedelta(days=i)
                    dia_str = dia.isoformat()
                    
                    vendas_dia = supabase.table('gb_vendas').select('gb_quantidade').gte(
                        'gb_data_criacao', dia_str + ' 00:00:00'
                    ).lt('gb_data_criacao', dia_str + ' 23:59:59').eq('gb_status', 'completed').execute()
                    
                    total_dia = sum(v['gb_quantidade'] for v in (vendas_dia.data or []))
                    
                    vendas_7_dias.append({
                        'data': dia_str,
                        'total': total_dia
                    })
                
                relatorio['vendas_7_dias'] = list(reversed(vendas_7_dias))
                
            except Exception as e:
                log_error("admin_relatorio_vendas", e)
        else:
            # Calcular em memória
            hoje_str = hoje.isoformat()
            
            for venda in memory_storage['vendas']:
                if venda.get('status') == 'completed':
                    if venda.get('tipo_jogo') == 'raspa_brasil':
                        relatorio['vendas_rb'] += venda.get('quantidade', 0)
                    elif venda.get('tipo_jogo') == '2para1000':
                        relatorio['vendas_ml'] += venda.get('quantidade', 0)
                    
                    relatorio['receita_total'] += venda.get('valor_total', 0)
                    
                    if venda.get('data_criacao', '')[:10] == hoje_str:
                        relatorio['vendas_hoje'] += venda.get('quantidade', 0)
            
            # Vendas dos últimos 7 dias em memória
            for i in range(7):
                dia = hoje - timedelta(days=i)
                dia_str = dia.isoformat()
                
                total_dia = sum(
                    v.get('quantidade', 0) for v in memory_storage['vendas']
                    if v.get('data_criacao', '')[:10] == dia_str and v.get('status') == 'completed'
                )
                
                vendas_7_dias.append({
                    'data': dia_str,
                    'total': total_dia
                })
            
            relatorio['vendas_7_dias'] = list(reversed(vendas_7_dias))
        
        log_info("admin_relatorio_vendas", f"Relatório gerado - RB: {relatorio['vendas_rb']}, ML: {relatorio['vendas_ml']}")
        return jsonify(relatorio)
        
    except Exception as e:
        log_error("admin_relatorio_vendas", e)
        return jsonify({
            'vendas_rb': 0,
            'vendas_ml': 0,
            'receita_total': 0,
            'vendas_hoje': 0,
            'vendas_7_dias': []
        })

# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando GANHA BRASIL - Sistema Integrado v3.0.2...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅ Real' if sdk else '🔄 Simulado'}")
    print(f"🔗 Supabase: {'✅ Conectado' if supabase else '🔄 Memória'}")
    print(f"📱 QR Code: {'✅ Disponível' if qrcode_available else '🔄 Texto'}")
    print(f"📄 PDF: {'✅ Disponível' if reportlab_available else '❌ Não disponível'}")
    print(f"🎮 Jogos Disponíveis:")
    print(f"   - RASPA BRASIL: Raspadinhas virtuais (R$ {PRECO_RASPADINHA_RB:.2f})")
    print(f"   - 2 PARA 1000: Bilhetes da milhar (R$ {PRECO_BILHETE_ML:.2f})")
    print(f"👤 Sistema de Login: ✅ IMPLEMENTADO (CPF único)")
    print(f"👥 Sistema de Afiliados: ✅ COMPLETO")
    print(f"🎯 Prêmios: Manual (RB) + Sorteio diário (ML)")
    print(f"🔄 Pagamentos: Via PIX (real/simulado)")
    print(f"📱 Interface: Responsiva e moderna")
    print(f"🛡️ Segurança: Login obrigatório + Validações")
    print(f"📊 Admin: Painel unificado completo")
    print(f"🔐 Senha Admin: {ADMIN_PASSWORD}")
    print(f"🎨 Frontend: Integração total com index.html")
    print(f"💾 Storage: Supabase com fallback em memória")
    print(f"🆕 CORREÇÕES V3.0.2:")
    print(f"   ✅ VALOR ACUMULA R$ 1000 (CORRIGIDO)")
    print(f"   ✅ Número sorteado permanece visível")
    print(f"   ✅ Ganhadores 2para1000 funcionando")
    print(f"   ✅ Resultado do sorteio não some mais")
    print(f"   ✅ Função admin_sortear corrigida")
    print(f"   ✅ Sistema de acúmulo de prêmio ajustado")
    print(f"✅ PROBLEMAS RESOLVIDOS - SISTEMA OPERACIONAL!")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
