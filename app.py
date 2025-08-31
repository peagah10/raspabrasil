import os
import random
import string
from datetime import datetime, date
from flask import Flask, request, jsonify, session, send_file
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

# Inicializar cliente Supabase com tratamento de erro melhorado
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Testar conexão
        test_response = supabase.table('br_configuracoes').select(
            'br_chave'
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


def log_payment_change(payment_id, status_anterior, status_novo,
                       webhook_data=None):
    """Registra mudanças de status de pagamento"""
    if not supabase or not payment_id:
        return False
    try:
        supabase.table('br_logs_pagamento').insert({
            'br_payment_id': str(payment_id),
            'br_status_anterior': status_anterior,
            'br_status_novo': status_novo,
            'br_webhook_data': webhook_data
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


def gerar_codigo_afiliado():
    """Gera código único para afiliado no formato AF-XXXXX"""
    numero = random.randint(100000, 999999)
    return f"AF{numero}"


def verificar_codigo_unico(codigo, tabela='br_ganhadores', campo='br_codigo'):
    """Verifica se o código é único no banco de dados"""
    if not supabase or not codigo:
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
        response = supabase.table('br_configuracoes').select('br_valor').eq(
            'br_chave', chave
        ).execute()
        if response.data:
            return response.data[0]['br_valor']
        return valor_padrao
    except Exception as e:
        print(f"❌ Erro ao obter configuração {chave}: {str(e)}")
        return valor_padrao


def atualizar_configuracao(chave, valor):
    """Atualiza valor de configuração no Supabase"""
    if not supabase or not chave:
        return False
    try:
        # Primeiro tentar update
        response = supabase.table('br_configuracoes').update({
            'br_valor': str(valor)
        }).eq('br_chave', chave).execute()
        
        # Se não existir, inserir
        if not response.data:
            response = supabase.table('br_configuracoes').insert({
                'br_chave': chave,
                'br_valor': str(valor)
            }).execute()
        
        return response.data is not None
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração {chave}: {str(e)}")
        return False


def obter_total_vendas():
    """Obtém total de vendas aprovadas do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('br_vendas').select('br_quantidade').eq(
            'br_status', 'completed'
        ).execute()
        if response.data:
            return sum(venda['br_quantidade'] for venda in response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de vendas: {str(e)}")
        return 0


def obter_total_ganhadores():
    """Obtém total de ganhadores do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('br_ganhadores').select('br_id').execute()
        if response.data:
            return len(response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de ganhadores: {str(e)}")
        return 0


def obter_total_afiliados():
    """Obtém total de afiliados ativos do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('br_afiliados').select('br_id').eq(
            'br_status', 'ativo'
        ).execute()
        if response.data:
            return len(response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de afiliados: {str(e)}")
        return 0


def obter_afiliado_por_codigo(codigo):
    """Busca afiliado pelo código"""
    if not supabase or not codigo:
        return None
    try:
        response = supabase.table('br_afiliados').select('*').eq(
            'br_codigo', codigo
        ).eq('br_status', 'ativo').execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar afiliado: {str(e)}")
        return None


def obter_afiliado_por_cpf(cpf):
    """Busca afiliado pelo CPF"""
    if not supabase or not cpf:
        return None
    try:
        response = supabase.table('br_afiliados').select('*').eq(
            'br_cpf', cpf
        ).eq('br_status', 'ativo').execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar afiliado por CPF: {str(e)}")
        return None


def registrar_click_afiliado(afiliado_id, ip_cliente, user_agent, referrer=''):
    """Registra click no link do afiliado"""
    if not supabase or not afiliado_id:
        return False
    try:
        supabase.table('br_afiliado_clicks').insert({
            'br_afiliado_id': afiliado_id,
            'br_ip_visitor': ip_cliente or 'unknown',
            'br_user_agent': (user_agent or '')[:500],
            'br_referrer': (referrer or '')[:500]
        }).execute()
        
        # Atualizar contador de clicks
        afiliado = supabase.table('br_afiliados').select('br_total_clicks').eq(
            'br_id', afiliado_id
        ).execute()
        
        if afiliado.data:
            novo_total = (afiliado.data[0]['br_total_clicks'] or 0) + 1
            supabase.table('br_afiliados').update({
                'br_total_clicks': novo_total
            }).eq('br_id', afiliado_id).execute()
        
        return True
    except Exception as e:
        print(f"❌ Erro ao registrar click: {str(e)}")
        return False


def calcular_comissao_afiliado(valor_venda):
    """Calcula comissão do afiliado"""
    if not valor_venda or valor_venda <= 0:
        return 0
    percentual = float(obter_configuracao('percentual_comissao_afiliado', '50'))
    return (valor_venda * percentual / 100)


def validar_pagamento_aprovado(payment_id):
    """Valida se o pagamento foi realmente aprovado - COM VALIDAÇÕES ROBUSTAS"""
    if not sdk or not payment_id:
        return False
    
    # Validar se payment_id não é None, undefined ou string vazia
    if payment_id in [None, 'undefined', 'null', '']:
        print(f"❌ Payment ID inválido: {payment_id}")
        return False

    try:
        payment_response = sdk.payment().get(str(payment_id))
        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment.get('status', '')
            print(f"🔍 Validação payment {payment_id}: status = {status}")
            return status == 'approved'
        else:
            print(f"❌ Erro na resposta MP para {payment_id}: {payment_response}")
            return False
    except Exception as e:
        print(f"❌ Erro ao validar pagamento {payment_id}: {str(e)}")
        return False


def verificar_raspadinhas_para_pagamento():
    """Verifica se há raspadinhas disponíveis para este pagamento específico - COM PROMOÇÃO 10+2"""
    try:
        payment_id = session.get('payment_id')
        if not payment_id or payment_id in ['undefined', 'null', '']:
            print("❌ Payment ID não encontrado na sessão")
            return False
            
        # Verificar se o pagamento foi aprovado
        if not validar_pagamento_aprovado(payment_id):
            print(f"❌ Pagamento {payment_id} não está aprovado")
            return False
            
        # Verificar quantas raspadinhas já foram usadas
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)
        quantidade_paga = session.get('quantidade', 0)
        
        # PROMOÇÃO 10+2: Se comprou exatamente 10, pode raspar 12
        quantidade_disponivel = quantidade_paga
        if quantidade_paga == 10:
            quantidade_disponivel = 12
        
        disponivel = raspadas < quantidade_disponivel
        print(f"🎮 Verificação raspadinhas - Payment: {payment_id}, Raspadas: {raspadas}/{quantidade_disponivel}, Disponível: {disponivel}")
        
        return disponivel
    except Exception as e:
        print(f"❌ Erro ao verificar raspadinhas: {str(e)}")
        return False


def sortear_premio_novo_sistema():
    """SISTEMA DE PRÊMIOS MANUAL - Só libera quando admin autorizar"""
    try:
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            print("⚠️ Sistema desativado pelo admin")
            return None

        # Verificar prêmio manual liberado pelo admin
        premio_manual = obter_configuracao('premio_manual_liberado', '')
        if premio_manual:
            # Limpar prêmio manual após uso e retornar
            atualizar_configuracao('premio_manual_liberado', '')
            print(f"✅ Prêmio manual liberado pelo admin: {premio_manual}")
            return premio_manual

        # SISTEMA BLOQUEADO - Não libera prêmios automáticos
        print("🎯 Sistema manual: Nenhum prêmio liberado pelo admin")
        return None

    except Exception as e:
        print(f"❌ Erro ao verificar prêmio liberado: {str(e)}")
        return None


@app.route('/')
def index():
    """Serve a página principal"""
    try:
        # Verificar se há código de afiliado na URL
        ref_code = request.args.get('ref')
        if ref_code:
            # Buscar afiliado e registrar click
            afiliado = obter_afiliado_por_codigo(ref_code)
            if afiliado:
                registrar_click_afiliado(
                    afiliado['br_id'],
                    request.remote_addr,
                    request.headers.get('User-Agent', ''),
                    request.headers.get('Referer', '')
                )
                print(f"✅ Click registrado para afiliado: {ref_code}")
        
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"""
        <h1>Erro ao carregar a página</h1>
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


@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago para notificações de pagamento"""
    try:
        data = request.json
        print(f"📬 Webhook recebido: {data}")
        
        # Verificar se é uma notificação de pagamento
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            if payment_id:
                print(f"🔔 Notificação de pagamento: {payment_id}")
                
                # Processar o pagamento automaticamente
                if supabase and sdk:
                    try:
                        # Buscar detalhes do pagamento
                        payment_response = sdk.payment().get(payment_id)
                        if payment_response["status"] == 200:
                            payment = payment_response["response"]
                            status = payment['status']
                            
                            # Atualizar status no banco
                            supabase.table('br_vendas').update({
                                'br_status': 'completed' if status == 'approved' else status
                            }).eq('br_payment_id', str(payment_id)).execute()
                            
                            print(f"📊 Status atualizado via webhook: {payment_id} -> {status}")
                            
                            # Log da mudança
                            log_payment_change(payment_id, 'pending', status, data)
                    except Exception as e:
                        print(f"❌ Erro ao processar webhook: {str(e)}")
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"❌ Erro no webhook: {str(e)}")
        return jsonify({'error': 'webhook_error'}), 500


@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX real via Mercado Pago - COM SUPORTE À PROMOÇÃO 10+2"""
    data = request.json
    quantidade = data.get('quantidade', 1)
    # IMPORTANTE: O valor sempre é baseado na quantidade original (10), não na promocional (12)
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

    # Buscar afiliado se houver código
    afiliado = None
    if afiliado_codigo:
        afiliado = obter_afiliado_por_codigo(afiliado_codigo)

    # Descrição especial para promoção 10+2
    descricao = f"Raspa Brasil - {quantidade} raspadinha(s)"
    if quantidade == 10:
        descricao = "Raspa Brasil - 10 raspadinhas (+2 GRÁTIS!)"

    payment_data = {
        "transaction_amount": float(total),
        "description": descricao,
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
        print(f"💳 Criando pagamento: R$ {total:.2f} ({descricao})")
        payment_response = sdk.payment().create(payment_data)

        if payment_response["status"] == 201:
            payment = payment_response["response"]

            session['payment_id'] = str(payment['id'])
            session['quantidade'] = quantidade  # Salva a quantidade original (10)
            session['payment_created_at'] = datetime.now().isoformat()
            if afiliado:
                session['afiliado_id'] = afiliado['br_id']

            if supabase:
                try:
                    venda_data = {
                        'br_quantidade': quantidade,  # Quantidade paga (10)
                        'br_valor_total': total,
                        'br_payment_id': str(payment['id']),
                        'br_status': 'pending',
                        'br_ip_cliente': request.remote_addr or 'unknown',
                        'br_user_agent': request.headers.get(
                            'User-Agent', ''
                        )[:500],
                        'br_raspadinhas_usadas': 0  # Novo campo para controle
                    }
                    
                    if afiliado:
                        venda_data['br_afiliado_id'] = afiliado['br_id']
                        comissao = calcular_comissao_afiliado(total)
                        venda_data['br_comissao_paga'] = 0  # Será atualizado quando aprovado
                    
                    supabase.table('br_vendas').insert(venda_data).execute()
                    print(f"💾 Venda registrada: Payment {payment['id']}")
                    
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


@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verifica status do pagamento no Mercado Pago - COM VALIDAÇÕES ROBUSTAS"""
    if not sdk:
        return jsonify({'error': 'Mercado Pago não configurado'}), 500
    
    # Validações robustas do payment_id
    if not payment_id or payment_id in ['undefined', 'null', '']:
        return jsonify({'error': 'Payment ID inválido'}), 400

    try:
        print(f"🔍 Verificando pagamento: {payment_id}")

        payment_response = sdk.payment().get(str(payment_id))

        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment['status']

            print(f"📊 Status do pagamento {payment_id}: {status}")

            # Se aprovado e ainda não processado, atualizar no Supabase
            payment_key = f'payment_processed_{payment_id}'
            if status == 'approved' and payment_key not in session:
                if supabase:
                    try:
                        # Buscar venda para calcular comissão
                        venda_response = supabase.table('br_vendas').select('*').eq(
                            'br_payment_id', str(payment_id)
                        ).execute()
                        
                        if venda_response.data:
                            venda = venda_response.data[0]
                            update_data = {'br_status': 'completed'}
                            
                            # Calcular e atualizar comissão se há afiliado
                            if venda.get('br_afiliado_id'):
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
                                    
                                    print(f"💰 Comissão de R$ {comissao:.2f} creditada ao afiliado {venda['br_afiliado_id']}")
                            
                            # Atualizar status da venda
                            supabase.table('br_vendas').update(update_data).eq(
                                'br_payment_id', str(payment_id)
                            ).execute()

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


@app.route('/verificar_raspadinhas_disponiveis', methods=['POST'])
def verificar_raspadinhas_disponiveis_route():
    """Endpoint para verificar se há raspadinhas disponíveis"""
    try:
        disponivel = verificar_raspadinhas_para_pagamento()
        return jsonify({'disponivel': disponivel})
    except Exception as e:
        print(f"❌ Erro ao verificar raspadinhas: {str(e)}")
        return jsonify({'disponivel': False})


@app.route('/raspar', methods=['POST'])
def raspar():
    """Processa raspagem - SISTEMA MANUAL COMPLETO COM PROMOÇÃO 10+2"""
    try:
        # Verificar se há raspadinhas disponíveis
        if not verificar_raspadinhas_para_pagamento():
            return jsonify({
                'ganhou': False,
                'erro': 'Pagamento não encontrado ou não aprovado. Pague primeiro para jogar.'
            }), 400

        # Obter dados da sessão
        payment_id = session.get('payment_id')
        quantidade_paga = session.get('quantidade', 0)
        raspadas_key = f'raspadas_{payment_id}'
        raspadas = session.get(raspadas_key, 0)

        # PROMOÇÃO 10+2: Determinar quantidade máxima permitida
        quantidade_maxima = quantidade_paga
        if quantidade_paga == 10:
            quantidade_maxima = 12

        # Incrementar contador de raspadas
        session[raspadas_key] = raspadas + 1

        # Atualizar contador no banco
        if supabase and payment_id:
            try:
                supabase.table('br_vendas').update({
                    'br_raspadinhas_usadas': raspadas + 1
                }).eq('br_payment_id', str(payment_id)).execute()
            except Exception as e:
                print(f"❌ Erro ao atualizar contador: {str(e)}")

        # Tentar sortear prêmio com sistema manual
        premio = sortear_premio_novo_sistema()

        if premio:
            codigo = gerar_codigo_unico()
            print(
                f"🎁 PRÊMIO LIBERADO: {premio} - "
                f"Código: {codigo} - Payment: {payment_id} - "
                f"Raspada: {raspadas + 1}/{quantidade_maxima}"
            )
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo
            })
        else:
            print(
                f"❌ Sem prêmio - Payment: {payment_id} - "
                f"Raspada: {raspadas + 1}/{quantidade_maxima} - "
                f"Promoção 10+2: {'SIM' if quantidade_paga == 10 else 'NÃO'}"
            )
            return jsonify({'ganhou': False})

    except Exception as e:
        print(f"❌ Erro ao processar raspagem: {str(e)}")
        return jsonify({'ganhou': False, 'erro': str(e)}), 500


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
        existing = supabase.table('br_ganhadores').select('br_id').eq(
            'br_codigo', data['codigo']
        ).execute()
        if existing.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Código já utilizado'
            })

        response = supabase.table('br_ganhadores').insert({
            'br_codigo': data['codigo'],
            'br_nome': data['nome'].strip()[:255],
            'br_valor': data['valor'],
            'br_chave_pix': data['chave_pix'].strip()[:255],
            'br_tipo_chave': data['tipo_chave'],
            'br_telefone': data.get('telefone', '')[:20],
            'br_status_pagamento': 'pendente'
        }).execute()

        if response.data:
            print(
                f"🏆 Ganhador salvo: {data['nome']} - "
                f"{data['valor']} - {data['codigo']}"
            )
            return jsonify({'sucesso': True, 'id': response.data[0]['br_id']})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir ganhador'
            })

    except Exception as e:
        print(f"❌ Erro ao salvar ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/criar_saque_ganhador', methods=['POST'])
def criar_saque_ganhador():
    """Cria automaticamente uma solicitação de saque para o ganhador"""
    try:
        data = request.json
        
        # Validar dados obrigatórios
        campos_obrigatorios = ['ganhador_id', 'nome', 'valor', 'chave_pix', 'codigo']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                print(f"❌ Campo obrigatório ausente: {campo}")
                return jsonify({'sucesso': False, 'erro': f'Campo {campo} é obrigatório'})
        
        if not supabase:
            print("❌ Supabase não conectado")
            return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
        # Extrair valor numérico do prêmio
        valor_texto = data['valor']
        try:
            # Remover R$, espaços e converter vírgula para ponto
            valor_limpo = valor_texto.replace('R$', '').replace(' ', '').replace(',', '.')
            valor_numerico = float(valor_limpo)
        except (ValueError, AttributeError):
            print(f"❌ Erro ao converter valor: {valor_texto}")
            return jsonify({'sucesso': False, 'erro': 'Valor inválido'})
        
        # Criar solicitação de saque
        saque_data = {
            'br_ganhador_id': data['ganhador_id'],
            'br_valor': valor_numerico,
            'br_chave_pix': data['chave_pix'],
            'br_tipo_chave': data.get('tipo_chave', 'cpf'),
            'br_status': 'solicitado',
            'br_data_solicitacao': datetime.now().isoformat()
        }
        
        response = supabase.table('br_saques_ganhadores').insert(saque_data).execute()
        
        if response.data:
            print(f"💸 Saque criado automaticamente: {data['nome']} - {valor_texto} - Código: {data['codigo']}")
            return jsonify({
                'sucesso': True, 
                'saque_id': response.data[0]['br_id'],
                'valor': valor_numerico
            })
        else:
            print(f"❌ Erro ao inserir saque no banco")
            return jsonify({'sucesso': False, 'erro': 'Erro ao criar saque'})
            
    except Exception as e:
        print(f"❌ Erro ao criar saque de ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': f'Erro interno: {str(e)}'})
        
    return jsonify({'sucesso': False, 'erro': 'Erro desconhecido'})


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
        existing_email = supabase.table('br_afiliados').select('br_id').eq(
            'br_email', data['email']
        ).execute()
        
        existing_cpf = supabase.table('br_afiliados').select('br_id').eq(
            'br_cpf', cpf
        ).execute()
        
        if existing_email.data or existing_cpf.data:
            return jsonify({
                'sucesso': False,
                'erro': 'E-mail ou CPF já cadastrado'
            })

        # Gerar código único
        codigo = gerar_codigo_afiliado_unico()

        # Inserir afiliado
        response = supabase.table('br_afiliados').insert({
            'br_codigo': codigo,
            'br_nome': data['nome'].strip()[:255],
            'br_email': data['email'].strip().lower()[:255],
            'br_telefone': data['telefone'].strip()[:20],
            'br_cpf': cpf,
            'br_status': 'ativo'
        }).execute()

        if response.data:
            afiliado = response.data[0]
            print(f"👤 Novo afiliado cadastrado: {data['nome']} - {codigo}")
            
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
                    'chave_pix': afiliado['br_chave_pix'],
                    'tipo_chave_pix': afiliado['br_tipo_chave_pix']
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

        response = supabase.table('br_afiliados').update({
            'br_chave_pix': chave_pix,
            'br_tipo_chave_pix': tipo_chave
        }).eq('br_codigo', codigo).eq('br_status', 'ativo').execute()

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
        afiliado_response = supabase.table('br_afiliados').select('*').eq(
            'br_codigo', codigo
        ).eq('br_status', 'ativo').execute()

        if not afiliado_response.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Afiliado não encontrado'
            })

        afiliado = afiliado_response.data[0]
        saldo = float(afiliado['br_saldo_disponivel'] or 0)
        saque_minimo = float(obter_configuracao('saque_minimo_afiliado', '10'))

        if saldo < saque_minimo:
            return jsonify({
                'sucesso': False,
                'erro': f'Saldo insuficiente. Mínimo: R$ {saque_minimo:.2f}'
            })

        if not afiliado['br_chave_pix']:
            return jsonify({
                'sucesso': False,
                'erro': 'Configure sua chave PIX primeiro'
            })

        # Inserir solicitação de saque
        saque_response = supabase.table('br_saques_afiliados').insert({
            'br_afiliado_id': afiliado['br_id'],
            'br_valor': saldo,
            'br_chave_pix': afiliado['br_chave_pix'],
            'br_tipo_chave': afiliado['br_tipo_chave_pix'],
            'br_status': 'solicitado',
            'br_data_solicitacao': datetime.now().isoformat()
        }).execute()

        if saque_response.data:
            # Zerar saldo do afiliado
            supabase.table('br_afiliados').update({
                'br_saldo_disponivel': 0
            }).eq('br_id', afiliado['br_id']).execute()

            print(f"💸 Saque solicitado: {afiliado['br_nome']} - R$ {saldo:.2f}")

            return jsonify({
                'sucesso': True,
                'valor': saldo,
                'saque_id': saque_response.data[0]['br_id']
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao processar saque'
            })

    except Exception as e:
        print(f"❌ Erro ao solicitar saque: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


# ========== ROTAS ADMIN ATUALIZADAS ==========

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login do admin"""
    data = request.json
    senha = data.get('senha')
    
    if not senha:
        return jsonify({'success': False, 'message': 'Senha é obrigatória'})
    
    # Senha padrão admin
    if senha == 'paulo10@admin':
        session['admin_logado'] = True
        return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
    
    # Verificar no banco se existir
    if supabase:
        try:
            response = supabase.table('br_admins').select('*').eq(
                'br_senha', senha
            ).eq('br_ativo', True).execute()
            if response.data:
                admin = response.data[0]
                session['admin_logado'] = True
                session['admin_usuario'] = admin['br_usuario']
                
                # Atualizar último login
                supabase.table('br_admins').update({
                    'br_ultimo_login': datetime.now().isoformat()
                }).eq('br_id', admin['br_id']).execute()
                
                return jsonify({'success': True, 'message': f'Bem-vindo, {admin["br_nome"]}'})
        except Exception as e:
            print(f"❌ Erro ao verificar admin no banco: {str(e)}")
    
    return jsonify({'success': False, 'message': 'Senha incorreta'})


@app.route('/admin/liberar_premio_manual', methods=['POST'])
def admin_liberar_premio_manual():
    """Libera prêmio manual para próxima raspagem"""
    if not session.get('admin_logado'):
        return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
    
    try:
        data = request.json
        valor = data.get('valor')
        
        if not valor:
            return jsonify({'sucesso': False, 'erro': 'Valor é obrigatório'})
        
        # Validar formato básico
        valor = valor.strip()
        if not valor.startswith('R$'):
            return jsonify({'sucesso': False, 'erro': 'Formato inválido. Use: R$ 00,00'})
        
        # Salvar prêmio manual
        if atualizar_configuracao('premio_manual_liberado', valor):
            print(f"🎯 Prêmio manual liberado pelo admin: {valor}")
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar configuração'})
        
    except Exception as e:
        print(f"❌ Erro ao liberar prêmio: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/admin/verificar_status_premio')
def admin_verificar_status_premio():
    """Verifica se há prêmio liberado aguardando"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'}), 403
    
    try:
        premio_liberado = obter_configuracao('premio_manual_liberado', '')
        
        if premio_liberado:
            return jsonify({
                'premio_liberado': True,
                'valor': premio_liberado
            })
        else:
            return jsonify({
                'premio_liberado': False,
                'valor': None
            })
    except Exception as e:
        print(f"❌ Erro ao verificar status do prêmio: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/pagamentos_orfaos')
def admin_pagamentos_orfaos():
    """Lista pagamentos aprovados sem raspadinhas usadas - COM SUPORTE PROMOÇÃO 10+2 E VALIDAÇÕES ROBUSTAS"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if not supabase:
        return jsonify({'pagamentos': []})
    
    try:
        # Buscar vendas aprovadas onde as raspadinhas não foram totalmente usadas
        response = supabase.table('br_vendas').select('*').eq(
            'br_status', 'completed'
        ).execute()
        
        pagamentos_orfaos = []
        
        for venda in (response.data or []):
            # Validações robustas
            payment_id = venda.get('br_payment_id')
            if not payment_id or payment_id in ['undefined', 'null', '']:
                continue
                
            quantidade_paga = venda.get('br_quantidade', 0)
            raspadinhas_usadas = venda.get('br_raspadinhas_usadas', 0)
            
            # PROMOÇÃO 10+2: Ajustar quantidade esperada
            quantidade_esperada = quantidade_paga
            if quantidade_paga == 10:
                quantidade_esperada = 12
            
            # Se pagou mas não raspou todas (ou nenhuma)
            if raspadinhas_usadas < quantidade_esperada:
                # Verificar se realmente está aprovado no Mercado Pago
                if validar_pagamento_aprovado(payment_id):
                    # Garantir que todos os campos necessários existem
                    venda_segura = {
                        'rb_payment_id': payment_id,
                        'rb_valor_total': venda.get('br_valor_total', 0),
                        'rb_quantidade': quantidade_paga,
                        'rb_raspadinhas_usadas': raspadinhas_usadas,
                        'rb_data_criacao': venda.get('br_data_criacao', ''),
                        'rb_ip_cliente': venda.get('br_ip_cliente', 'N/A'),
                        'rb_afiliado_id': venda.get('br_afiliado_id')
                    }
                    pagamentos_orfaos.append(venda_segura)
        
        print(f"📊 Encontrados {len(pagamentos_orfaos)} pagamentos órfãos (considerando promoção 10+2)")
        return jsonify({'pagamentos': pagamentos_orfaos})
        
    except Exception as e:
        print(f"❌ Erro ao buscar pagamentos órfãos: {str(e)}")
        return jsonify({'pagamentos': [], 'erro': str(e)})


@app.route('/admin/processar_devolucao', methods=['POST'])
def admin_processar_devolucao():
    """Processa devolução de pagamento órfão - COM VALIDAÇÕES ROBUSTAS"""
    if not session.get('admin_logado'):
        return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
    
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
    
    try:
        data = request.json
        payment_id = data.get('payment_id')
        
        # Validações robustas
        if not payment_id or payment_id in ['undefined', 'null', '']:
            return jsonify({'sucesso': False, 'erro': 'Payment ID inválido ou não fornecido'})
        
        # Buscar venda
        venda_response = supabase.table('br_vendas').select('*').eq(
            'br_payment_id', str(payment_id)
        ).execute()
        
        if not venda_response.data:
            return jsonify({'sucesso': False, 'erro': 'Venda não encontrada no banco de dados'})
        
        venda = venda_response.data[0]
        
        # Verificar se já não foi devolvida
        if venda.get('br_status') == 'refunded':
            return jsonify({'sucesso': False, 'erro': 'Este pagamento já foi devolvido'})
        
        # Marcar como devolvida
        supabase.table('br_vendas').update({
            'br_status': 'refunded',
            'br_data_devolucao': datetime.now().isoformat()
        }).eq('br_payment_id', str(payment_id)).execute()
        
        # Se havia afiliado, reverter comissão
        if venda.get('br_afiliado_id') and venda.get('br_comissao_paga', 0) > 0:
            afiliado_response = supabase.table('br_afiliados').select('*').eq(
                'br_id', venda['br_afiliado_id']
            ).execute()
            
            if afiliado_response.data:
                afiliado = afiliado_response.data[0]
                comissao_revertida = float(venda.get('br_comissao_paga', 0))
                
                # Atualizar totais do afiliado (evitar valores negativos)
                novo_total_vendas = max(0, (afiliado['br_total_vendas'] or 0) - venda['br_quantidade'])
                nova_total_comissao = max(0, (afiliado['br_total_comissao'] or 0) - comissao_revertida)
                novo_saldo = max(0, (afiliado['br_saldo_disponivel'] or 0) - comissao_revertida)
                
                supabase.table('br_afiliados').update({
                    'br_total_vendas': novo_total_vendas,
                    'br_total_comissao': nova_total_comissao,
                    'br_saldo_disponivel': novo_saldo
                }).eq('br_id', venda['br_afiliado_id']).execute()
                
                print(f"💰 Comissão de R$ {comissao_revertida:.2f} revertida do afiliado {venda['br_afiliado_id']}")
        
        print(f"💸 Devolução processada para payment {payment_id}")
        
        # Log da devolução
        log_payment_change(
            payment_id, 'completed', 'refunded', {
                'source': 'admin_devolucao',
                'amount': venda.get('br_valor_total', 0),
                'admin_user': session.get('admin_usuario', 'admin')
            }
        )
        
        return jsonify({'sucesso': True, 'mensagem': 'Devolução processada com sucesso'})
        
    except Exception as e:
        print(f"❌ Erro ao processar devolução: {str(e)}")
        return jsonify({'sucesso': False, 'erro': f'Erro interno: {str(e)}'})


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
        response = supabase.table('br_ganhadores').select('*').eq(
            'br_codigo', codigo
        ).execute()
        
        if response.data:
            ganhador = response.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'Código válido - {ganhador["br_nome"]} - {ganhador["br_valor"]} - Status: {ganhador.get("br_status_pagamento", "pendente")}'
            })
        else:
            return jsonify({'valido': False, 'mensagem': 'Código não encontrado ou inválido'})
            
    except Exception as e:
        print(f"❌ Erro ao validar código: {str(e)}")
        return jsonify({'valido': False, 'mensagem': 'Erro ao validar código'})


@app.route('/admin/premiados')
def admin_premiados():
    """Lista de premiados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'premiados': []})
    
    try:
        response = supabase.table('br_ganhadores').select('*').order(
            'br_data_criacao', desc=True
        ).limit(50).execute()
        return jsonify({'premiados': response.data or []})
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
        response = supabase.table('br_afiliados').select('*').order(
            'br_data_criacao', desc=True
        ).execute()
        
        afiliados = []
        for afiliado in response.data or []:
            afiliados.append({
                'id': afiliado['br_id'],
                'codigo': afiliado['br_codigo'],
                'nome': afiliado['br_nome'],
                'email': afiliado['br_email'],
                'telefone': afiliado['br_telefone'],
                'total_clicks': afiliado['br_total_clicks'] or 0,
                'total_vendas': afiliado['br_total_vendas'] or 0,
                'total_comissao': float(afiliado['br_total_comissao'] or 0),
                'saldo_disponivel': float(afiliado['br_saldo_disponivel'] or 0),
                'status': afiliado['br_status'],
                'data_criacao': afiliado['br_data_criacao']
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
        saques_response = supabase.table('br_saques_ganhadores').select('*').order(
            'br_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do ganhador separadamente
            ganhador_response = supabase.table('br_ganhadores').select('br_nome, br_codigo').eq(
                'br_id', saque['br_ganhador_id']
            ).execute()
            
            saque_completo = saque.copy()
            if ganhador_response.data:
                saque_completo['br_ganhadores'] = ganhador_response.data[0]
            else:
                saque_completo['br_ganhadores'] = {'br_nome': 'Nome não encontrado', 'br_codigo': 'N/A'}
            
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
        saques_response = supabase.table('br_saques_afiliados').select('*').order(
            'br_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do afiliado separadamente
            afiliado_response = supabase.table('br_afiliados').select('br_nome, br_codigo, br_total_vendas').eq(
                'br_id', saque['br_afiliado_id']
            ).execute()
            
            saque_completo = saque.copy()
            if afiliado_response.data:
                saque_completo['br_afiliados'] = afiliado_response.data[0]
            else:
                saque_completo['br_afiliados'] = {'br_nome': 'Nome não encontrado', 'br_codigo': 'N/A', 'br_total_vendas': 0}
            
            saques.append(saque_completo)
        
        return jsonify({'saques': saques})
    except Exception as e:
        print(f"❌ Erro ao listar saques de afiliados: {str(e)}")
        return jsonify({'saques': []})


@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema incluindo afiliados - CORRIGIDA PARA CONTAR RASPADINHAS"""
    try:
        vendidas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()
        afiliados = obter_total_afiliados()
        
        # Estatísticas do dia
        vendas_hoje = 0
        vendas_afiliados_hoje = 0
        if supabase:
            try:
                hoje = date.today().isoformat()
                vendas_response = supabase.table('br_vendas').select('*').gte(
                    'br_data_criacao', hoje + ' 00:00:00'
                ).eq('br_status', 'completed').execute()
                
                for venda in (vendas_response.data or []):
                    # Contar raspadinhas vendidas (não vendas)
                    quantidade = venda.get('br_quantidade', 0)
                    vendas_hoje += quantidade
                    
                    if venda.get('br_afiliado_id'):
                        vendas_afiliados_hoje += quantidade
                
            except Exception as e:
                print(f"❌ Erro ao obter vendas do dia: {str(e)}")

        # Prêmios restantes (sempre 0 no sistema manual)
        total_premios_restantes = 0

        return jsonify({
            'vendidas': vendidas,
            'ganhadores': ganhadores,
            'afiliados': afiliados,
            'vendas_hoje': vendas_hoje,
            'vendas_afiliados_hoje': vendas_afiliados_hoje,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS - vendidas,
            'premios_restantes': total_premios_restantes,
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
            'supabase_conectado': False,
            'mercadopago_conectado': False,
            'sistema_ativo': True
        })


# ========== ROTAS DE SAQUE ==========

@app.route('/admin/pagar_saque_ganhador/<int:saque_id>', methods=['POST'])
def pagar_saque_ganhador(saque_id):
    """Marca saque de ganhador como pago"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        response = supabase.table('br_saques_ganhadores').update({
            'br_status': 'pago',
            'br_data_pagamento': datetime.now().isoformat()
        }).eq('br_id', saque_id).execute()
        
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
        check_response = supabase.table('br_saques_ganhadores').select('br_status').eq(
            'br_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['br_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('br_saques_ganhadores').delete().eq(
            'br_id', saque_id
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
        response = supabase.table('br_saques_afiliados').update({
            'br_status': 'pago',
            'br_data_pagamento': datetime.now().isoformat()
        }).eq('br_id', saque_id).execute()
        
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
        check_response = supabase.table('br_saques_afiliados').select('br_status').eq(
            'br_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['br_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('br_saques_afiliados').delete().eq(
            'br_id', saque_id
        ).execute()
        
        return jsonify({"sucesso": True, "mensagem": "Saque excluído com sucesso"})
        
    except Exception as e:
        print(f"❌ Erro ao excluir saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando Raspa Brasil ATUALIZADO COM PROMOÇÃO 10+2...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"👥 Sistema de Afiliados: ✅")
    print(f"🎯 Sistema de Prêmios: MANUAL COMPLETO")
    print(f"🔄 Sistema de Persistência: ✅")
    print(f"🎁 Promoção 10+2: ✅ ATIVA")
    print(f"⚙️ Área Admin: LIBERADA PARA GESTÃO MANUAL")
    print(f"🛡️ Validações Robustas: ✅ IMPLEMENTADAS")
    print(f"📬 Webhook Mercado Pago: ✅ IMPLEMENTADO")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
