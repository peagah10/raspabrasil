import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_file, Response
from dotenv import load_dotenv
import json
import traceback

# Inicializar Supabase
try:
    from supabase import create_client, Client
    supabase_available = True
except ImportError:
    supabase_available = False
    print("⚠️ Supabase não disponível")

try:
    import mercadopago
    mercadopago_available = True
except ImportError:
    mercadopago_available = False
    print("⚠️ MercadoPago não disponível")

import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'portal-jogos-secret-key-2024')

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
APP_VERSION = "2.1.0"

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
        supabase = None

# Configurar Mercado Pago
try:
    if MP_ACCESS_TOKEN and mercadopago_available:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        print("✅ Mercado Pago SDK configurado com sucesso")
    else:
        print("❌ Token do Mercado Pago não encontrado ou biblioteca não disponível")
except Exception as e:
    print(f"❌ Erro ao configurar Mercado Pago: {str(e)}")

# ========== FUNÇÕES AUXILIARES ==========

def log_error(operation, error, extra_data=None):
    """Log de erros centralizado"""
    print(f"❌ [{operation}] {str(error)}")
    if extra_data:
        print(f"   Dados extras: {extra_data}")
    
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

def log_info(operation, message, extra_data=None):
    """Log de informações centralizado"""
    print(f"ℹ️ [{operation}] {message}")
    if extra_data:
        print(f"   Dados: {extra_data}")

def log_payment_change(payment_id, status_anterior, status_novo, webhook_data=None):
    """Registra mudanças de status de pagamento"""
    if not supabase or not payment_id:
        return False
    try:
        supabase.table('br_logs_pagamento').insert({
            'br_payment_id': str(payment_id),
            'br_status_anterior': status_anterior,
            'br_status_novo': status_novo,
            'br_webhook_data': webhook_data,
            'br_timestamp': datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        log_error("log_payment_change", e, {"payment_id": payment_id})
        return False

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

def verificar_codigo_unico(codigo, tabela='br_ganhadores', campo='br_codigo'):
    """Verifica se o código é único no banco de dados"""
    if not supabase or not codigo:
        return True
    try:
        response = supabase.table(tabela).select(campo).eq(campo, codigo).execute()
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

def gerar_codigo_afiliado_unico():
    """Gera um código de afiliado único"""
    max_tentativas = 10
    for _ in range(max_tentativas):
        codigo = gerar_codigo_afiliado()
        if verificar_codigo_unico(codigo, 'br_afiliados', 'br_codigo'):
            return codigo
    return f"AF{random.randint(100000, 999999)}"

def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração do Supabase"""
    if not supabase or not chave:
        return valor_padrao
    try:
        # Tentar na tabela de configurações RB primeiro
        response = supabase.table('br_configuracoes').select('br_valor').eq('br_chave', chave).execute()
        if response.data:
            return response.data[0]['br_valor']
        
        # Tentar na tabela ML
        response = supabase.table('ml_configuracoes').select('ml_valor').eq('ml_chave', chave).execute()
        if response.data:
            return response.data[0]['ml_valor']
        
        return valor_padrao
    except Exception as e:
        log_error("obter_configuracao", e, {"chave": chave})
        return valor_padrao

def atualizar_configuracao(chave, valor, game_type='raspa_brasil'):
    """Atualiza valor de configuração no Supabase"""
    if not supabase or not chave:
        return False
    try:
        tabela = 'br_configuracoes' if game_type == 'raspa_brasil' else 'ml_configuracoes'
        campo_chave = 'br_chave' if game_type == 'raspa_brasil' else 'ml_chave'
        campo_valor = 'br_valor' if game_type == 'raspa_brasil' else 'ml_valor'
        
        # Tentar atualizar primeiro
        response = supabase.table(tabela).update({
            campo_valor: str(valor)
        }).eq(campo_chave, chave).execute()
        
        # Se não existe, inserir
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

def obter_total_vendas(game_type='raspa_brasil'):
    """Obtém total de vendas aprovadas do Supabase"""
    if not supabase:
        return 0
    try:
        tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
        campo_quantidade = 'br_quantidade' if game_type == 'raspa_brasil' else 'ml_quantidade'
        campo_status = 'br_status' if game_type == 'raspa_brasil' else 'ml_status'
        
        response = supabase.table(tabela).select(campo_quantidade).eq(campo_status, 'completed').execute()
        if response.data:
            total = sum(venda[campo_quantidade] for venda in response.data)
            log_info("obter_total_vendas", f"Total {game_type}: {total}")
            return total
        return 0
    except Exception as e:
        log_error("obter_total_vendas", e, {"game_type": game_type})
        return 0

def obter_total_ganhadores(game_type='raspa_brasil'):
    """Obtém total de ganhadores do Supabase"""
    if not supabase:
        return 0
    try:
        tabela = 'br_ganhadores' if game_type == 'raspa_brasil' else 'ml_ganhadores'
        campo_id = 'br_id' if game_type == 'raspa_brasil' else 'ml_id'
        
        response = supabase.table(tabela).select(campo_id).execute()
        if response.data:
            total = len(response.data)
            log_info("obter_total_ganhadores", f"Total {game_type}: {total}")
            return total
        return 0
    except Exception as e:
        log_error("obter_total_ganhadores", e, {"game_type": game_type})
        return 0

def obter_total_afiliados():
    """Obtém total de afiliados ativos do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('br_afiliados').select('br_id').eq('br_status', 'ativo').execute()
        if response.data:
            total = len(response.data)
            log_info("obter_total_afiliados", f"Total afiliados ativos: {total}")
            return total
        return 0
    except Exception as e:
        log_error("obter_total_afiliados", e)
        return 0

def obter_afiliado_por_codigo(codigo):
    """Busca afiliado pelo código"""
    if not supabase or not codigo:
        return None
    try:
        response = supabase.table('br_afiliados').select('*').eq('br_codigo', codigo).eq('br_status', 'ativo').execute()
        if response.data:
            afiliado = response.data[0]
            log_info("obter_afiliado_por_codigo", f"Afiliado encontrado: {codigo} - {afiliado['br_nome']}")
            return afiliado
        return None
    except Exception as e:
        log_error("obter_afiliado_por_codigo", e, {"codigo": codigo})
        return None

def obter_afiliado_por_cpf(cpf):
    """Busca afiliado pelo CPF"""
    if not supabase or not cpf:
        return None
    try:
        response = supabase.table('br_afiliados').select('*').eq('br_cpf', cpf).eq('br_status', 'ativo').execute()
        if response.data:
            afiliado = response.data[0]
            log_info("obter_afiliado_por_cpf", f"Afiliado encontrado: {cpf} - {afiliado['br_nome']}")
            return afiliado
        return None
    except Exception as e:
        log_error("obter_afiliado_por_cpf", e, {"cpf": cpf})
        return None

def registrar_click_afiliado(afiliado_id, ip_cliente, user_agent, referrer=''):
    """Registra click no link do afiliado"""
    if not supabase or not afiliado_id:
        return False
    try:
        # Registrar click
        supabase.table('br_afiliado_clicks').insert({
            'br_afiliado_id': afiliado_id,
            'br_ip_visitor': ip_cliente or 'unknown',
            'br_user_agent': (user_agent or '')[:500],
            'br_referrer': (referrer or '')[:500]
        }).execute()
        
        # Atualizar contador do afiliado
        afiliado = supabase.table('br_afiliados').select('br_total_clicks').eq('br_id', afiliado_id).execute()
        
        if afiliado.data:
            novo_total = (afiliado.data[0]['br_total_clicks'] or 0) + 1
            supabase.table('br_afiliados').update({
                'br_total_clicks': novo_total
            }).eq('br_id', afiliado_id).execute()
            
            log_info("registrar_click_afiliado", f"Click registrado para afiliado {afiliado_id}, total: {novo_total}")
        
        return True
    except Exception as e:
        log_error("registrar_click_afiliado", e, {"afiliado_id": afiliado_id})
        return False

def calcular_comissao_afiliado(valor_venda):
    """Calcula comissão do afiliado"""
    if not valor_venda or valor_venda <= 0:
        return 0
    percentual = float(obter_configuracao('percentual_comissao_afiliado', '50'))
    comissao = (valor_venda * percentual / 100)
    log_info("calcular_comissao_afiliado", f"{percentual}% de R$ {valor_venda:.2f} = R$ {comissao:.2f}")
    return comissao

def validar_pagamento_aprovado(payment_id):
    """Valida se o pagamento foi realmente aprovado"""
    if not sdk or not payment_id:
        return False
    
    if payment_id in [None, 'undefined', 'null', '']:
        log_error("validar_pagamento_aprovado", "Payment ID inválido", {"payment_id": payment_id})
        return False

    try:
        payment_response = sdk.payment().get(str(payment_id))
        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment.get('status', '')
            log_info("validar_pagamento_aprovado", f"Payment {payment_id}: status = {status}")
            return status == 'approved'
        else:
            log_error("validar_pagamento_aprovado", f"Erro na resposta MP para {payment_id}", payment_response)
            return False
    except Exception as e:
        log_error("validar_pagamento_aprovado", e, {"payment_id": payment_id})
        return False

def verificar_raspadinhas_para_pagamento():
    """Verifica se há raspadinhas disponíveis para este pagamento específico"""
    try:
        payment_id = session.get('payment_id')
        if not payment_id or payment_id in ['undefined', 'null', '']:
            log_error("verificar_raspadinhas_para_pagamento", "Payment ID não encontrado na sessão")
            return False
            
        if not validar_pagamento_aprovado(payment_id):
            log_error("verificar_raspadinhas_para_pagamento", f"Pagamento {payment_id} não está aprovado")
            return False
            
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)
        quantidade_paga = session.get('quantidade', 0)
        
        quantidade_disponivel = quantidade_paga
        if quantidade_paga == 10:
            quantidade_disponivel = 12
        
        disponivel = raspadas < quantidade_disponivel
        log_info("verificar_raspadinhas_para_pagamento", 
                f"Payment: {payment_id}, Raspadas: {raspadas}/{quantidade_disponivel}, Disponível: {disponivel}")
        
        return disponivel
    except Exception as e:
        log_error("verificar_raspadinhas_para_pagamento", e)
        return False

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

def atualizar_premio_acumulado(novo_valor):
    """Atualiza valor do prêmio acumulado do 2 para 1000"""
    return atualizar_configuracao('premio_acumulado', str(novo_valor), '2para1000')

def validar_session_admin():
    """Valida se o usuário está logado como admin"""
    return session.get('admin_logado', False)

def sanitizar_dados_entrada(data):
    """Sanitiza dados de entrada para evitar problemas de segurança"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()[:500]  # Limitar tamanho
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, str):
        return data.strip()[:500]
    return data

# ========== ROTAS PRINCIPAIS ==========

@app.route('/')
def index():
    """Serve a página principal unificada"""
    try:
        ref_code = request.args.get('ref')
        if ref_code:
            afiliado = obter_afiliado_por_codigo(ref_code)
            if afiliado:
                registrar_click_afiliado(
                    afiliado['br_id'],
                    request.remote_addr,
                    request.headers.get('User-Agent', ''),
                    request.headers.get('Referer', '')
                )
                log_info("index", f"Click registrado para afiliado: {ref_code}")
        
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content
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
    """Health check avançado para o Render"""
    try:
        # Testar conexões
        supabase_status = False
        mercadopago_status = False
        
        if supabase:
            try:
                test = supabase.table('br_vendas').select('br_id').limit(1).execute()
                supabase_status = True
            except:
                pass
        
        if sdk:
            mercadopago_status = True
        
        # Estatísticas básicas
        stats = {
            'total_vendas_rb': obter_total_vendas('raspa_brasil'),
            'total_vendas_ml': obter_total_vendas('2para1000'),
            'total_afiliados': obter_total_afiliados(),
            'total_ganhadores_rb': obter_total_ganhadores('raspa_brasil'),
            'total_ganhadores_ml': obter_total_ganhadores('2para1000'),
            'premio_acumulado': obter_premio_acumulado()
        }
        
        return {
            'status': 'healthy' if supabase_status else 'degraded',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'services': {
                'supabase': supabase_status,
                'mercadopago': mercadopago_status,
                'flask': True
            },
            'games': ['raspa_brasil', '2para1000'],
            'features': ['afiliados', 'admin', 'pagamentos_unificados', 'sistema_manual_premios'],
            'statistics': stats,
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
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'error': str(e)
        }, 500

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago para notificações de pagamento"""
    try:
        data = request.json
        log_info("webhook_mercadopago", f"Webhook recebido: {data}")
        
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            if payment_id:
                log_info("webhook_mercadopago", f"Processando payment: {payment_id}")
                
                if supabase and sdk:
                    try:
                        payment_response = sdk.payment().get(payment_id)
                        if payment_response["status"] == 200:
                            payment = payment_response["response"]
                            status = payment['status']
                            
                            # Atualizar em ambas as tabelas
                            supabase.table('br_vendas').update({
                                'br_status': 'completed' if status == 'approved' else status
                            }).eq('br_payment_id', str(payment_id)).execute()
                            
                            supabase.table('ml_vendas').update({
                                'ml_status': 'completed' if status == 'approved' else status
                            }).eq('ml_payment_id', str(payment_id)).execute()
                            
                            log_info("webhook_mercadopago", f"Status atualizado: {payment_id} -> {status}")
                            log_payment_change(payment_id, 'pending', status, data)
                            
                    except Exception as e:
                        log_error("webhook_mercadopago", e, {"payment_id": payment_id})
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        log_error("webhook_mercadopago", e)
        return jsonify({'error': 'webhook_error'}), 500

# ========== ROTAS DE PAGAMENTO ==========

@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX real via Mercado Pago - Unificado para ambos os jogos"""
    try:
        data = sanitizar_dados_entrada(request.json)
        quantidade = data.get('quantidade', 1)
        game_type = data.get('game_type', 'raspa_brasil')
        afiliado_codigo = data.get('ref_code') or session.get('ref_code')

        # Validações básicas
        if not isinstance(quantidade, int) or quantidade < 1 or quantidade > 50:
            return jsonify({
                'error': 'Quantidade inválida',
                'details': 'A quantidade deve ser entre 1 e 50'
            }), 400

        if game_type not in ['raspa_brasil', '2para1000']:
            return jsonify({
                'error': 'Tipo de jogo inválido',
                'details': 'Use raspa_brasil ou 2para1000'
            }), 400

        # Determinar preço por unidade baseado no jogo
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        total = quantidade * preco_unitario

        log_info("create_payment", f"Criando pagamento: {game_type} - {quantidade} unidades - R$ {total:.2f}")

        if not sdk:
            return jsonify({
                'error': 'Sistema de pagamento temporariamente indisponível.',
                'details': 'Tente novamente em alguns minutos.'
            }), 500

        # Verificar disponibilidade (apenas para Raspa Brasil)
        if game_type == 'raspa_brasil':
            vendidas = obter_total_vendas('raspa_brasil')
            if vendidas + quantidade > TOTAL_RASPADINHAS:
                return jsonify({
                    'error': 'Raspadinhas esgotadas',
                    'details': f'Restam apenas {TOTAL_RASPADINHAS - vendidas} disponíveis'
                }), 400

        # Buscar afiliado se houver código
        afiliado = None
        if afiliado_codigo:
            afiliado = obter_afiliado_por_codigo(afiliado_codigo)
            if afiliado:
                log_info("create_payment", f"Venda com afiliado: {afiliado['br_nome']} ({afiliado_codigo})")

        # Descrição do pagamento
        if game_type == 'raspa_brasil':
            descricao = f"Raspa Brasil - {quantidade} raspadinha(s)"
            if quantidade == 10:
                descricao = "Raspa Brasil - 10 raspadinhas (+2 GRÁTIS!)"
        else:
            descricao = f"2 para 1000 - {quantidade} bilhete(s)"

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

            # Salvar na sessão
            session['payment_id'] = str(payment['id'])
            session['quantidade'] = quantidade
            session['game_type'] = game_type
            session['payment_created_at'] = datetime.now().isoformat()
            if afiliado:
                session['afiliado_id'] = afiliado['br_id']

            # Salvar no banco
            if supabase:
                try:
                    # Escolher tabela baseada no tipo de jogo
                    tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
                    
                    if game_type == 'raspa_brasil':
                        venda_data = {
                            'br_quantidade': quantidade,
                            'br_valor_total': total,
                            'br_payment_id': str(payment['id']),
                            'br_status': 'pending',
                            'br_ip_cliente': request.remote_addr or 'unknown',
                            'br_user_agent': request.headers.get('User-Agent', '')[:500],
                            'br_raspadinhas_usadas': 0
                        }
                        
                        if afiliado:
                            venda_data['br_afiliado_id'] = afiliado['br_id']
                            venda_data['br_comissao_paga'] = 0
                    else:
                        venda_data = {
                            'ml_quantidade': quantidade,
                            'ml_valor_total': total,
                            'ml_payment_id': str(payment['id']),
                            'ml_status': 'pending',
                            'ml_ip_cliente': request.remote_addr or 'unknown'
                        }
                        
                        if afiliado:
                            venda_data['ml_afiliado_id'] = afiliado['br_id']
                    
                    response = supabase.table(tabela).insert(venda_data).execute()
                    log_info("create_payment", f"Venda registrada: Payment {payment['id']} - {game_type}")
                    
                except Exception as e:
                    log_error("create_payment", e, {"payment_id": payment['id']})

            pix_data = payment.get('point_of_interaction', {}).get('transaction_data', {})

            if not pix_data:
                return jsonify({'error': 'Erro ao gerar dados PIX'}), 500

            log_info("create_payment", f"Pagamento criado com sucesso: {payment['id']} - R$ {total:.2f}")

            return jsonify({
                'id': payment['id'],
                'qr_code': pix_data.get('qr_code', ''),
                'qr_code_base64': pix_data.get('qr_code_base64', ''),
                'status': payment['status'],
                'amount': payment['transaction_amount']
            })
        else:
            log_error("create_payment", "Erro na resposta do MP", payment_response)
            return jsonify({
                'error': 'Erro ao criar pagamento',
                'details': payment_response.get('message', 'Erro desconhecido')
            }), 500

    except Exception as e:
        log_error("create_payment", e)
        return jsonify({
            'error': 'Erro interno do servidor',
            'details': 'Tente novamente em alguns minutos'
        }), 500

@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verifica status do pagamento no Mercado Pago - Unificado"""
    try:
        if not sdk:
            return jsonify({'error': 'Sistema de pagamento indisponível'}), 500
        
        if not payment_id or payment_id in ['undefined', 'null', '']:
            return jsonify({'error': 'Payment ID inválido'}), 400

        log_info("check_payment", f"Verificando pagamento: {payment_id}")

        payment_response = sdk.payment().get(str(payment_id))

        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment['status']

            log_info("check_payment", f"Status do pagamento {payment_id}: {status}")

            # Processar pagamento aprovado
            payment_key = f'payment_processed_{payment_id}'
            if status == 'approved' and payment_key not in session:
                if supabase:
                    try:
                        game_type = session.get('game_type', 'raspa_brasil')
                        
                        # Atualizar na tabela apropriada
                        tabela = 'br_vendas' if game_type == 'raspa_brasil' else 'ml_vendas'
                        campo_payment = 'br_payment_id' if game_type == 'raspa_brasil' else 'ml_payment_id'
                        campo_status = 'br_status' if game_type == 'raspa_brasil' else 'ml_status'
                        
                        venda_response = supabase.table(tabela).select('*').eq(campo_payment, str(payment_id)).execute()
                        
                        if venda_response.data:
                            venda = venda_response.data[0]
                            update_data = {campo_status: 'completed'}
                            
                            # Processar comissão se houver afiliado
                            if game_type == 'raspa_brasil' and venda.get('br_afiliado_id'):
                                comissao = calcular_comissao_afiliado(venda['br_valor_total'])
                                update_data['br_comissao_paga'] = comissao
                                
                                # Atualizar saldo do afiliado
                                afiliado_atual = supabase.table('br_afiliados').select('*').eq(
                                    'br_id', venda['br_afiliado_id']
                                ).execute()
                                
                                if afiliado_atual.data:
                                    afiliado = afiliado_atual.data[0]
                                    novo_total_vendas = (afiliado['br_total_vendas'] or 0) + venda['br_quantidade']
                                    nova_total_comissao = (afiliado['br_total_comissao'] or 0) + comissao
                                    novo_saldo = (afiliado['br_saldo_disponivel'] or 0) + comissao
                                    
                                    supabase.table('br_afiliados').update({
                                        'br_total_vendas': novo_total_vendas,
                                        'br_total_comissao': nova_total_comissao,
                                        'br_saldo_disponivel': novo_saldo
                                    }).eq('br_id', venda['br_afiliado_id']).execute()
                                    
                                    log_info("check_payment", f"Comissão de R$ {comissao:.2f} creditada ao afiliado")
                            
                            elif game_type == '2para1000' and venda.get('ml_afiliado_id'):
                                comissao = calcular_comissao_afiliado(venda['ml_valor_total'])
                                
                                # Atualizar saldo do afiliado
                                afiliado_atual = supabase.table('br_afiliados').select('*').eq(
                                    'br_id', venda['ml_afiliado_id']
                                ).execute()
                                
                                if afiliado_atual.data:
                                    afiliado = afiliado_atual.data[0]
                                    novo_total_vendas = (afiliado['br_total_vendas'] or 0) + venda['ml_quantidade']
                                    nova_total_comissao = (afiliado['br_total_comissao'] or 0) + comissao
                                    novo_saldo = (afiliado['br_saldo_disponivel'] or 0) + comissao
                                    
                                    supabase.table('br_afiliados').update({
                                        'br_total_vendas': novo_total_vendas,
                                        'br_total_comissao': nova_total_comissao,
                                        'br_saldo_disponivel': novo_saldo
                                    }).eq('br_id', venda['ml_afiliado_id']).execute()
                                    
                                    log_info("check_payment", f"Comissão ML de R$ {comissao:.2f} creditada ao afiliado")
                            
                            # Atualizar status da venda
                            supabase.table(tabela).update(update_data).eq(campo_payment, str(payment_id)).execute()

                            session[payment_key] = True
                            log_info("check_payment", f"Pagamento aprovado e processado: {payment_id}")

                            log_payment_change(payment_id, 'pending', 'completed', {
                                'source': 'check_payment',
                                'amount': payment.get('transaction_amount', 0),
                                'game_type': game_type
                            })

                    except Exception as e:
                        log_error("check_payment", e, {"payment_id": payment_id})

            return jsonify({
                'status': status,
                'amount': payment.get('transaction_amount', 0),
                'description': payment.get('description', ''),
                'date_created': payment.get('date_created', ''),
                'date_approved': payment.get('date_approved', '')
            })
        else:
            log_error("check_payment", f"Erro ao verificar pagamento: {payment_response}")
            return jsonify({'error': 'Erro ao verificar pagamento'}), 500

    except Exception as e:
        log_error("check_payment", e, {"payment_id": payment_id})
        return jsonify({'error': str(e)}), 500

# ========== ROTAS RASPA BRASIL ==========

@app.route('/raspar', methods=['POST'])
def raspar():
    """Processa raspagem - Sistema manual completo com promoção 10+2"""
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
        if supabase and payment_id:
            try:
                supabase.table('br_vendas').update({
                    'br_raspadinhas_usadas': raspadas + 1
                }).eq('br_payment_id', str(payment_id)).execute()
                log_info("raspar", f"Contador atualizado: {raspadas + 1}/{quantidade_maxima} para payment {payment_id}")
            except Exception as e:
                log_error("raspar", e, {"payment_id": payment_id})

        # Verificar se há prêmio liberado pelo admin
        premio = sortear_premio_novo_sistema()

        if premio:
            codigo = gerar_codigo_unico()
            log_info("raspar", f"PRÊMIO LIBERADO: {premio} - Código: {codigo} - Payment: {payment_id}")
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo
            })
        else:
            log_info("raspar", f"Sem prêmio - Payment: {payment_id} - Raspada: {raspadas + 1}/{quantidade_maxima}")
            return jsonify({'ganhou': False})

    except Exception as e:
        log_error("raspar", e)
        return jsonify({'ganhou': False, 'erro': 'Erro interno do servidor'}), 500

@app.route('/salvar_ganhador', methods=['POST'])
def salvar_ganhador():
    """Salva dados do ganhador no Supabase"""
    try:
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['codigo', 'nome', 'valor', 'chave_pix', 'tipo_chave']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        # Validações
        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        if len(data['chave_pix']) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})

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
            log_info("salvar_ganhador", f"Ganhador salvo: {data['nome']} - {data['valor']} - {data['codigo']}")
            return jsonify({'sucesso': True, 'id': response.data[0]['br_id']})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao inserir ganhador'})

    except Exception as e:
        log_error("salvar_ganhador", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS 2 PARA 1000 ==========

@app.route('/enviar_bilhete', methods=['POST'])
def enviar_bilhete():
    """Salva dados do cliente e seus bilhetes do 2 para 1000"""
    try:
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['nome', 'telefone', 'chave_pix', 'bilhetes']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

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
            log_info("enviar_bilhete", f"Cliente registrado: {data['nome']} - Bilhetes: {data['bilhetes']} - Payment: {payment_id}")
            return jsonify({'sucesso': True, 'id': response.data[0]['ml_id']})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar dados'})

    except Exception as e:
        log_error("enviar_bilhete", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/resultado_sorteio')
def resultado_sorteio():
    """Obtém resultado do sorteio do dia do 2 para 1000"""
    try:
        if not supabase:
            return jsonify({
                'milhar_sorteada': None,
                'houve_ganhador': False,
                'valor_acumulado': f"{PREMIO_INICIAL_ML:.2f}".replace('.', ',')
            })

        hoje = date.today().isoformat()
        
        response = supabase.table('ml_sorteios').select('*').eq('ml_data_sorteio', hoje).execute()

        if response.data:
            sorteio = response.data[0]
            valor_acumulado = obter_premio_acumulado()
            
            log_info("resultado_sorteio", f"Resultado: {sorteio['ml_milhar_sorteada']} - Ganhador: {sorteio['ml_houve_ganhador']}")
            
            return jsonify({
                'milhar_sorteada': sorteio['ml_milhar_sorteada'],
                'houve_ganhador': sorteio['ml_houve_ganhador'],
                'valor_premio': sorteio.get('ml_valor_premio', ''),
                'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
            })
        else:
            valor_acumulado = obter_premio_acumulado()
            log_info("resultado_sorteio", f"Nenhum sorteio hoje. Prêmio acumulado: R$ {valor_acumulado:.2f}")
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
        if not supabase:
            return jsonify({'ganhadores': []})

        response = supabase.table('ml_ganhadores').select(
            'ml_nome, ml_valor, ml_milhar_sorteada, ml_bilhete_premiado, ml_data_sorteio'
        ).order('ml_data_sorteio', desc=True).limit(10).execute()

        ganhadores = []
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
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)

        campos_obrigatorios = ['nome', 'email', 'telefone', 'cpf']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        # Validações
        cpf = data['cpf'].replace('.', '').replace('-', '').replace(' ', '')
        if len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})

        if '@' not in data['email'] or len(data['email']) < 5:
            return jsonify({'sucesso': False, 'erro': 'E-mail inválido'})

        if len(data['nome']) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})

        # Verificar duplicatas
        existing_email = supabase.table('br_afiliados').select('br_id').eq('br_email', data['email']).execute()
        existing_cpf = supabase.table('br_afiliados').select('br_id').eq('br_cpf', cpf).execute()
        
        if existing_email.data:
            return jsonify({'sucesso': False, 'erro': 'E-mail já cadastrado'})
        
        if existing_cpf.data:
            return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})

        codigo = gerar_codigo_afiliado_unico()

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
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/login_afiliado', methods=['POST'])
def login_afiliado():
    """Login do afiliado por CPF"""
    try:
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})

        afiliado = obter_afiliado_por_cpf(cpf)
        
        if afiliado:
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
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/atualizar_pix_afiliado', methods=['POST'])
def atualizar_pix_afiliado():
    """Atualiza chave PIX do afiliado"""
    try:
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')

        if not codigo or not chave_pix:
            return jsonify({
                'sucesso': False,
                'erro': 'Código e chave PIX são obrigatórios'
            })

        if len(chave_pix) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})

        response = supabase.table('br_afiliados').update({
            'br_chave_pix': chave_pix,
            'br_tipo_chave_pix': tipo_chave
        }).eq('br_codigo', codigo).eq('br_status', 'ativo').execute()

        if response.data:
            log_info("atualizar_pix_afiliado", f"PIX atualizado para afiliado {codigo}: {tipo_chave} - {chave_pix}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

    except Exception as e:
        log_error("atualizar_pix_afiliado", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/solicitar_saque_afiliado', methods=['POST'])
def solicitar_saque_afiliado():
    """Processa solicitação de saque do afiliado"""
    try:
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)
        codigo = data.get('codigo')
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código do afiliado é obrigatório'})

        afiliado_response = supabase.table('br_afiliados').select('*').eq('br_codigo', codigo).eq('br_status', 'ativo').execute()

        if not afiliado_response.data:
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})

        afiliado = afiliado_response.data[0]
        saldo = float(afiliado['br_saldo_disponivel'] or 0)
        saque_minimo = float(obter_configuracao('saque_minimo_afiliado', '10'))

        if saldo < saque_minimo:
            return jsonify({
                'sucesso': False,
                'erro': f'Saldo insuficiente. Mínimo: R$ {saque_minimo:.2f}'
            })

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
        
        # Verificar senha padrão ou configurada
        senha_configurada = obter_configuracao('admin_password', ADMIN_PASSWORD)
        
        if senha == senha_configurada:
            session['admin_logado'] = True
            session['admin_login_time'] = datetime.now().isoformat()
            log_info("admin_login", f"Admin logado com sucesso")
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
        
        stats = {}
        
        if game in ['raspa_brasil', 'both']:
            vendidas_rb = obter_total_vendas('raspa_brasil')
            ganhadores_rb = obter_total_ganhadores('raspa_brasil')
            afiliados = obter_total_afiliados()
            
            stats.update({
                'vendidas': vendidas_rb,
                'ganhadores': ganhadores_rb,
                'afiliados': afiliados,
                'total_raspadinhas': TOTAL_RASPADINHAS,
                'restantes': TOTAL_RASPADINHAS - vendidas_rb,
                'premios_restantes': 0,
                'sistema_ativo': obter_configuracao('sistema_ativo', 'true').lower() == 'true'
            })
        
        if game in ['2para1000', 'both']:
            vendidos_ml = obter_total_vendas('2para1000')
            ganhadores_ml = obter_total_ganhadores('2para1000')
            premio_atual = obter_premio_acumulado()
            
            stats.update({
                'bilhetes_vendidos': vendidos_ml,
                'total_ganhadores': ganhadores_ml,
                'premio_atual': f"{premio_atual:.2f}".replace('.', ',')
            })
        
        # Estatísticas do dia
        if supabase:
            try:
                hoje = date.today().isoformat()
                
                if game in ['raspa_brasil', 'both']:
                    vendas_rb_hoje = supabase.table('br_vendas').select('br_quantidade').gte(
                        'br_data_criacao', hoje + ' 00:00:00'
                    ).eq('br_status', 'completed').execute()
                    
                    vendas_hoje_rb = sum(v['br_quantidade'] for v in (vendas_rb_hoje.data or []))
                    stats['vendas_hoje'] = vendas_hoje_rb
                
                if game in ['2para1000', 'both']:
                    vendas_ml_hoje = supabase.table('ml_vendas').select('ml_quantidade').gte(
                        'ml_data_criacao', hoje + ' 00:00:00'
                    ).eq('ml_status', 'completed').execute()
                    
                    vendas_hoje_ml = sum(v['ml_quantidade'] for v in (vendas_ml_hoje.data or []))
                    stats['vendas_hoje_ml'] = vendas_hoje_ml
                
            except Exception as e:
                log_error("admin_stats", e)

        log_info("admin_stats", f"Stats consultadas - Game: {game}")
        return jsonify(stats)

    except Exception as e:
        log_error("admin_stats", e)
        return jsonify({
            'vendidas': 0,
            'bilhetes_vendidos': 0,
            'ganhadores': 0,
            'total_ganhadores': 0,
            'afiliados': 0,
            'vendas_hoje': 0,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS,
            'premios_restantes': 0,
            'premio_atual': f"{PREMIO_INICIAL_ML:.2f}".replace('.', ','),
            'sistema_ativo': True
        })

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

        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})

        data = sanitizar_dados_entrada(request.json)
        milhar_sorteada = data.get('milhar_sorteada', '').strip()

        if not milhar_sorteada or len(milhar_sorteada) != 4 or not milhar_sorteada.isdigit():
            return jsonify({'sucesso': False, 'erro': 'Milhar deve ter exatamente 4 dígitos'})

        hoje = date.today().isoformat()

        # Verificar se já foi sorteado hoje
        existing = supabase.table('ml_sorteios').select('ml_id').eq('ml_data_sorteio', hoje).execute()

        if existing.data:
            return jsonify({'sucesso': False, 'erro': 'Sorteio já foi realizado hoje'})

        # Buscar clientes participantes
        clientes_response = supabase.table('ml_clientes').select('*').eq('ml_data_sorteio', hoje).execute()

        houve_ganhador = False
        ganhador_data = None
        valor_premio = obter_premio_acumulado()

        # Verificar se algum bilhete ganhou
        for cliente in (clientes_response.data or []):
            bilhetes = cliente['ml_bilhetes']
            if milhar_sorteada in bilhetes:
                houve_ganhador = True
                ganhador_data = cliente
                log_info("admin_sortear", f"GANHADOR ENCONTRADO: {cliente['ml_nome']} - Bilhete: {milhar_sorteada}")
                break

        if houve_ganhador:
            # Salvar ganhador
            supabase.table('ml_ganhadores').insert({
                'ml_nome': ganhador_data['ml_nome'],
                'ml_telefone': ganhador_data['ml_telefone'],
                'ml_chave_pix': ganhador_data['ml_chave_pix'],
                'ml_bilhete_premiado': milhar_sorteada,
                'ml_milhar_sorteada': milhar_sorteada,
                'ml_valor': f"R$ {valor_premio:.2f}".replace('.', ','),
                'ml_data_sorteio': hoje,
                'ml_status_pagamento': 'pendente',
                'ml_ip_cliente': ganhador_data.get('ml_ip_cliente', 'unknown')
            }).execute()

            # Resetar prêmio
            atualizar_premio_acumulado(PREMIO_INICIAL_ML)
            novo_valor_acumulado = PREMIO_INICIAL_ML

            log_info("admin_sortear", f"GANHADOR! {ganhador_data['ml_nome']} - Bilhete: {milhar_sorteada} - Prêmio: R$ {valor_premio:.2f}")

        else:
            # Acumular prêmio
            novo_valor_acumulado = valor_premio + PREMIO_INICIAL_ML
            atualizar_premio_acumulado(novo_valor_acumulado)

            log_info("admin_sortear", f"Prêmio acumulado! Novo valor: R$ {novo_valor_acumulado:.2f}")

        # Salvar resultado do sorteio
        supabase.table('ml_sorteios').insert({
            'ml_data_sorteio': hoje,
            'ml_milhar_sorteada': milhar_sorteada,
            'ml_houve_ganhador': houve_ganhador,
            'ml_valor_premio': f"R$ {valor_premio:.2f}".replace('.', ',') if houve_ganhador else '',
            'ml_novo_valor_acumulado': f"R$ {novo_valor_acumulado:.2f}".replace('.', ','),
            'ml_admin_responsavel': session.get('admin_login_time', 'unknown')
        }).execute()

        return jsonify({
            'sucesso': True,
            'houve_ganhador': houve_ganhador,
            'ganhador': {
                'nome': ganhador_data['ml_nome'] if ganhador_data else '',
                'bilhete': milhar_sorteada
            } if houve_ganhador else None,
            'valor_premio': f"{valor_premio:.2f}".replace('.', ','),
            'novo_valor_acumulado': f"{novo_valor_acumulado:.2f}".replace('.', ',')
        })

    except Exception as e:
        log_error("admin_sortear", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS AUXILIARES DO ADMIN ==========

@app.route('/admin/ganhadores/<game>')
def admin_ganhadores(game):
    """Obtém lista de ganhadores para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'ganhadores': []})
        
        data_filtro = request.args.get('data')
        ganhadores = []
        
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
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})
        
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
            codigo = gerar_codigo_unico()
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
            
        elif jogo == '2para1000':
            bilhete = data.get('bilhete_premiado', '').strip()
            if not bilhete or len(bilhete) != 4 or not bilhete.isdigit():
                return jsonify({'sucesso': False, 'erro': 'Bilhete deve ter 4 dígitos'})
            
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
        else:
            return jsonify({'sucesso': False, 'erro': 'Jogo inválido'})
        
        if response.data:
            log_info("admin_adicionar_ganhador", f"Ganhador manual adicionado: {nome} - {valor} - {jogo}")
            return jsonify({'sucesso': True})
        else:
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
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})
        
        data = sanitizar_dados_entrada(request.json)
        ganhador_id = data.get('id')
        jogo = data.get('jogo')
        status = data.get('status')
        
        if not all([ganhador_id, jogo, status]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if status not in ['pendente', 'pago']:
            return jsonify({'sucesso': False, 'erro': 'Status inválido'})
        
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
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/remover_ganhador', methods=['POST'])
def admin_remover_ganhador():
    """Remove ganhador"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})
        
        data = sanitizar_dados_entrada(request.json)
        ganhador_id = data.get('id')
        jogo = data.get('jogo')
        
        if not all([ganhador_id, jogo]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
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
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/afiliados')
def admin_afiliados():
    """Obtém dados dos afiliados para o admin"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'afiliados': []})
        
        response = supabase.table('br_afiliados').select('*').eq('br_status', 'ativo').order('br_total_comissao', desc=True).limit(100).execute()
        
        afiliados = []
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
        
        if not supabase:
            return jsonify({'saques': []})
        
        query = supabase.table('br_saques_afiliados').select('''
            br_id, br_valor, br_chave_pix, br_tipo_chave, br_status, br_data_solicitacao,
            br_afiliados (br_nome, br_codigo)
        ''')
        
        if status == 'pendente':
            query = query.eq('br_status', 'solicitado')
        elif status == 'pago':
            query = query.eq('br_status', 'pago')
        
        response = query.order('br_data_solicitacao', desc=True).limit(100).execute()
        
        saques = []
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
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})
        
        data = sanitizar_dados_entrada(request.json)
        saque_id = data.get('saque_id')
        
        if not saque_id:
            return jsonify({'sucesso': False, 'erro': 'ID do saque é obrigatório'})
        
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
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/admin/bilhetes/<data_filtro>')
def admin_bilhetes(data_filtro):
    """Obtém bilhetes vendidos por data"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'bilhetes': []})
        
        response = supabase.table('ml_clientes').select('*').eq('ml_data_sorteio', data_filtro).order('ml_data_criacao', desc=True).execute()
        
        bilhetes = []
        for b in (response.data or []):
            bilhetes.append({
                'nome': b['ml_nome'],
                'telefone': b['ml_telefone'],
                'chave_pix': b['ml_chave_pix'],
                'bilhetes': b['ml_bilhetes'],
                'payment_id': b['ml_payment_id'],
                'data_sorteio': b['ml_data_sorteio']
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
        
        if not supabase:
            return jsonify({'vendas': [], 'estatisticas': {}})
        
        # Buscar vendas do dia
        response = supabase.table('br_vendas').select('*').gte(
            'br_data_criacao', data_filtro + ' 00:00:00'
        ).lt('br_data_criacao', data_filtro + ' 23:59:59').order('br_data_criacao', desc=True).execute()
        
        vendas = []
        total_vendidas = 0
        total_usadas = 0
        
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
        
        if not supabase:
            return jsonify({'vendas': []})
        
        # Últimos 7 dias
        sete_dias_atras = (datetime.now() - timedelta(days=7)).date().isoformat()
        
        vendas_rb = supabase.table('br_vendas').select('*').gte('br_data_criacao', sete_dias_atras).eq('br_status', 'completed').execute()
        vendas_ml = supabase.table('ml_vendas').select('*').gte('ml_data_criacao', sete_dias_atras).eq('ml_status', 'completed').execute()
        
        vendas = []
        
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
        
        if not supabase:
            return jsonify({'ganhadores': []})
        
        ganhadores = []
        
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
        
        log_info("admin_lista_ganhadores_dia", f"Lista de ganhadores do dia {data_filtro}: {len(ganhadores)} encontrados")
        return jsonify({'ganhadores': ganhadores})
        
    except Exception as e:
        log_error("admin_lista_ganhadores_dia", e)
        return jsonify({'ganhadores': []})

# ========== ROTAS DE LOGS E DEBUGGING ==========

@app.route('/admin/logs')
def admin_logs():
    """Obtém logs do sistema para debugging"""
    try:
        if not validar_session_admin():
            return jsonify({'error': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'logs': []})
        
        # Últimos logs
        response = supabase.table('br_logs_sistema').select('*').order('br_timestamp', desc=True).limit(50).execute()
        
        logs = []
        for log in (response.data or []):
            logs.append({
                'operacao': log['br_operacao'],
                'erro': log['br_erro'],
                'timestamp': log['br_timestamp'],
                'dados_extras': log.get('br_dados_extras')
            })
        
        return jsonify({'logs': logs})
        
    except Exception as e:
        log_error("admin_logs", e)
        return jsonify({'logs': []})

@app.route('/admin/clear_logs', methods=['POST'])
def admin_clear_logs():
    """Limpa logs antigos do sistema"""
    try:
        if not validar_session_admin():
            return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema temporariamente indisponível'})
        
        # Deletar logs mais antigos que 7 dias
        sete_dias_atras = (datetime.now() - timedelta(days=7)).isoformat()
        
        response = supabase.table('br_logs_sistema').delete().lt('br_timestamp', sete_dias_atras).execute()
        
        log_info("admin_clear_logs", "Logs antigos limpos")
        return jsonify({'sucesso': True})
        
    except Exception as e:
        log_error("admin_clear_logs", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando GANHA BRASIL - Sistema Integrado v2.1.0...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"🎮 Jogos Disponíveis:")
    print(f"   - RASPA BRASIL: Raspadinhas virtuais (R$ {PRECO_RASPADINHA_RB:.2f})")
    print(f"   - 2 PARA 1000: Bilhetes da milhar (R$ {PRECO_BILHETE_ML:.2f})")
    print(f"👥 Sistema de Afiliados: ✅ UNIFICADO")
    print(f"🎯 Prêmios: Manual (RB) + Sorteio diário (ML)")
    print(f"🔄 Pagamentos: Via PIX unificado")
    print(f"📱 Interface: Responsiva e moderna")
    print(f"🛡️ Segurança: Validações robustas")
    print(f"📊 Admin: Painel unificado completo")
    print(f"🔐 Senha Admin: {ADMIN_PASSWORD}")
    print(f"🎨 Frontend: Integração total com index.html")
    print(f"🔧 MELHORIAS V2.1.0:")
    print(f"   - Sistema de logs centralizado e melhorado")
    print(f"   - Validações de segurança aprimoradas")
    print(f"   - Sanitização de dados de entrada")
    print(f"   - Controle de sessão de admin melhorado")
    print(f"   - Tratamento de erros mais robusto")
    print(f"   - Sistema de debugging avançado")
    print(f"   - Validações de dados mais rigorosas")
    print(f"   - Logs de auditoria para ações administrativas")
    print(f"   - Health check mais detalhado")
    print(f"   - Prevenção contra ataques básicos")
    print(f"✅ SISTEMA TOTALMENTE FUNCIONAL E OTIMIZADO!")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)

