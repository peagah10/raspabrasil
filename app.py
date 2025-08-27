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


def obter_premios_disponiveis():
    """Obtém prêmios disponíveis do Supabase"""
    try:
        premios = {
            'R$ 10,00': int(obter_configuracao('premios_r10', '100')),
            'R$ 20,00': int(obter_configuracao('premios_r20', '50')),
            'R$ 30,00': int(obter_configuracao('premios_r30', '30')),
            'R$ 40,00': int(obter_configuracao('premios_r40', '20')),
            'R$ 50,00': int(obter_configuracao('premios_r50', '15')),
            'R$ 100,00': int(obter_configuracao('premios_r100', '10'))
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
            'R$ 100,00': 10
        }


def sortear_premio():
    """Sorteia prêmio baseado na probabilidade e disponibilidade"""
    try:
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            return None

        # Verificar se já passou do limite para liberar prêmios
        total_vendas = obter_total_vendas()
        limite_premios = int(obter_configuracao('limite_premios', '1000'))

        if total_vendas < limite_premios:
            print(f"🚫 Prêmios bloqueados: {total_vendas}/{limite_premios}")
            return None

        # Chance de ganhar configurável
        chance_ganhar = float(obter_configuracao('chance_ganhar', '0.25'))
        if random.random() > chance_ganhar:
            return None

        # Obter prêmios disponíveis
        premios = obter_premios_disponiveis()

        # Criar lista ponderada de prêmios (menor valor = maior chance)
        premios_ponderados = []
        pesos = {
            'R$ 10,00': 40, 'R$ 20,00': 25, 'R$ 30,00': 15,
            'R$ 40,00': 10, 'R$ 50,00': 7, 'R$ 100,00': 3
        }

        for valor, quantidade in premios.items():
            if quantidade > 0:
                peso = pesos.get(valor, 1)
                premios_ponderados.extend([valor] * peso)

        if not premios_ponderados:
            print("🚫 Nenhum prêmio disponível")
            return None

        # Sortear prêmio
        premio = random.choice(premios_ponderados)

        # Verificar se ainda há prêmios desse valor
        if premios[premio] <= 0:
            return None

        # Diminuir a quantidade do prêmio sorteado
        chave_premio = (
            f"premios_r{premio.replace('R$ ', '').replace(',00', '')}"
        )
        quantidade_atual = int(obter_configuracao(chave_premio, '0'))
        if quantidade_atual > 0:
            atualizar_configuracao(chave_premio, quantidade_atual - 1)
            print(
                f"🎉 Prêmio sorteado: {premio} - "
                f"Restam: {quantidade_atual - 1}"
            )
            return premio

        return None

    except Exception as e:
        print(f"❌ Erro ao sortear prêmio: {str(e)}")
        return None


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


def obter_total_ganhadores():
    """Obtém total de ganhadores do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('rb_ganhadores').select('rb_id').execute()
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
        response = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_status', 'ativo'
        ).execute()
        if response.data:
            return len(response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de afiliados: {str(e)}")
        return 0


def obter_afiliado_por_codigo(codigo):
    """Busca afiliado pelo código"""
    if not supabase:
        return None
    try:
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_codigo', codigo
        ).eq('rb_status', 'ativo').execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar afiliado: {str(e)}")
        return None


def obter_afiliado_por_cpf(cpf):
    """Busca afiliado pelo CPF"""
    if not supabase:
        return None
    try:
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_cpf', cpf
        ).eq('rb_status', 'ativo').execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar afiliado por CPF: {str(e)}")
        return None


def registrar_click_afiliado(afiliado_id, ip_cliente, user_agent, referrer=''):
    """Registra click no link do afiliado"""
    if not supabase:
        return False
    try:
        supabase.table('rb_afiliado_clicks').insert({
            'rb_afiliado_id': afiliado_id,
            'rb_ip_visitor': ip_cliente,
            'rb_user_agent': user_agent[:500],
            'rb_referrer': referrer[:500]
        }).execute()
        
        # Atualizar contador de clicks
        afiliado = supabase.table('rb_afiliados').select('rb_total_clicks').eq(
            'rb_id', afiliado_id
        ).execute()
        
        if afiliado.data:
            novo_total = (afiliado.data[0]['rb_total_clicks'] or 0) + 1
            supabase.table('rb_afiliados').update({
                'rb_total_clicks': novo_total
            }).eq('rb_id', afiliado_id).execute()
        
        return True
    except Exception as e:
        print(f"❌ Erro ao registrar click: {str(e)}")
        return False


def calcular_comissao_afiliado(valor_venda):
    """Calcula comissão do afiliado"""
    percentual = float(obter_configuracao('percentual_comissao_afiliado', '50'))
    return (valor_venda * percentual / 100)


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
                    afiliado['rb_id'],
                    request.remote_addr,
                    request.headers.get('User-Agent', ''),
                    request.headers.get('Referer', '')
                )
                print(f"📊 Click registrado para afiliado: {ref_code}")
        
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

    # Buscar afiliado se houver código
    afiliado = None
    if afiliado_codigo:
        afiliado = obter_afiliado_por_codigo(afiliado_codigo)

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
            if afiliado:
                session['afiliado_id'] = afiliado['rb_id']

            if supabase:
                try:
                    venda_data = {
                        'rb_quantidade': quantidade,
                        'rb_valor_total': total,
                        'rb_payment_id': str(payment['id']),
                        'rb_status': 'pending',
                        'rb_ip_cliente': request.remote_addr,
                        'rb_user_agent': request.headers.get(
                            'User-Agent', ''
                        )[:500]
                    }
                    
                    if afiliado:
                        venda_data['rb_afiliado_id'] = afiliado['rb_id']
                        comissao = calcular_comissao_afiliado(total)
                        venda_data['rb_comissao_paga'] = 0  # Será atualizado quando aprovado
                    
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
                        # Buscar venda para calcular comissão
                        venda_response = supabase.table('rb_vendas').select('*').eq(
                            'rb_payment_id', payment_id
                        ).execute()
                        
                        if venda_response.data:
                            venda = venda_response.data[0]
                            update_data = {'rb_status': 'completed'}
                            
                            # Calcular e atualizar comissão se há afiliado
                            if venda.get('rb_afiliado_id'):
                                comissao = calcular_comissao_afiliado(venda['rb_valor_total'])
                                update_data['rb_comissao_paga'] = comissao
                                
                                # Atualizar saldo do afiliado
                                afiliado_atual = supabase.table('rb_afiliados').select('*').eq(
                                    'rb_id', venda['rb_afiliado_id']
                                ).execute()
                                
                                if afiliado_atual.data:
                                    afiliado = afiliado_atual.data[0]
                                    novo_total_vendas = (afiliado['rb_total_vendas'] or 0) + venda['rb_quantidade']
                                    nova_total_comissao = (afiliado['rb_total_comissao'] or 0) + comissao
                                    novo_saldo = (afiliado['rb_saldo_disponivel'] or 0) + comissao
                                    
                                    supabase.table('rb_afiliados').update({
                                        'rb_total_vendas': novo_total_vendas,
                                        'rb_total_comissao': nova_total_comissao,
                                        'rb_saldo_disponivel': novo_saldo
                                    }).eq('rb_id', venda['rb_afiliado_id']).execute()
                                    
                                    print(f"💰 Comissão de R$ {comissao:.2f} creditada ao afiliado {venda['rb_afiliado_id']}")
                            
                            # Atualizar status da venda
                            supabase.table('rb_vendas').update(update_data).eq(
                                'rb_payment_id', payment_id
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


@app.route('/raspar', methods=['POST'])
def raspar():
    """Processa raspagem - REQUER PAGAMENTO APROVADO"""
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

        # Tentar sortear prêmio
        premio = sortear_premio()

        if premio:
            codigo = gerar_codigo_unico()
            print(
                f"🎉 Prêmio sorteado: {premio} - "
                f"Código: {codigo} - Payment: {payment_id}"
            )
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo
            })
        else:
            print(
                f"😔 Sem prêmio - Payment: {payment_id} - "
                f"Raspada: {raspadas + 1}/{quantidade_paga}"
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
            return jsonify({'sucesso': True, 'id': response.data[0]['rb_id']})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir ganhador'
            })

    except Exception as e:
        print(f"❌ Erro ao salvar ganhador: {str(e)}")
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
        afiliado = obter_afiliado_por_cpf(cpf)
        
        if afiliado:
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


@app.route('/afiliado/<codigo>')
def dados_afiliado(codigo):
    """Retorna dados do afiliado pelo código"""
    if not supabase:
        return jsonify({'erro': 'Sistema indisponível'}), 500

    try:
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_codigo', codigo
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
                    'total_clicks': afiliado['rb_total_clicks'],
                    'total_vendas': afiliado['rb_total_vendas'],
                    'total_comissao': float(afiliado['rb_total_comissao'] or 0),
                    'saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0),
                    'chave_pix': afiliado['rb_chave_pix'],
                    'tipo_chave_pix': afiliado['rb_tipo_chave_pix']
                }
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Afiliado não encontrado'
            }), 404

    except Exception as e:
        print(f"❌ Erro ao buscar afiliado: {str(e)}")
        return jsonify({'erro': str(e)}), 500


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
        saque_minimo = float(obter_configuracao('saque_minimo_afiliado', '10'))

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


# ========== ROTAS ADMIN ATUALIZADAS ==========

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login do admin"""
    data = request.json
    senha = data.get('senha')
    
    if not senha:
        return jsonify({'success': False, 'message': 'Senha é obrigatória'})
    
    # Por enquanto, usar senha simples até implementar tabela admin
    if senha == 'paulo10@admin':
        session['admin_logado'] = True
        return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
    
    # Verificar no banco se existir
    if supabase:
        try:
            response = supabase.table('rb_admins').select('*').eq(
                'rb_senha', senha
            ).eq('rb_ativo', True).execute()
            if response.data:
                admin = response.data[0]
                session['admin_logado'] = True
                session['admin_usuario'] = admin['rb_usuario']
                
                # Atualizar último login
                supabase.table('rb_admins').update({
                    'rb_ultimo_login': datetime.now().isoformat()
                }).eq('rb_id', admin['rb_id']).execute()
                
                return jsonify({'success': True, 'message': f'Bem-vindo, {admin["rb_nome"]}'})
        except Exception as e:
            print(f"❌ Erro ao verificar admin no banco: {str(e)}")
    
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
        response = supabase.table('rb_ganhadores').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if response.data:
            ganhador = response.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - {ganhador["rb_nome"]} - {ganhador["rb_valor"]} - Status: {ganhador.get("rb_status_pagamento", "pendente")}'
            })
        else:
            return jsonify({'valido': False, 'mensagem': '❌ Código não encontrado ou inválido'})
            
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
        response = supabase.table('rb_ganhadores').select('*').order(
            'rb_data_criacao', desc=True
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
            # Buscar dados do ganhador separadamente
            ganhador_response = supabase.table('rb_ganhadores').select('rb_nome, rb_codigo').eq(
                'rb_id', saque['rb_ganhador_id']
            ).execute()
            
            saque_completo = saque.copy()
            if ganhador_response.data:
                saque_completo['rb_ganhadores'] = ganhador_response.data[0]
            else:
                saque_completo['rb_ganhadores'] = {'rb_nome': 'Nome não encontrado', 'rb_codigo': 'N/A'}
            
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
            # Buscar dados do afiliado separadamente
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


@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema incluindo afiliados"""
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
                vendas_response = supabase.table('rb_vendas').select('*').gte(
                    'rb_data_criacao', hoje + ' 00:00:00'
                ).eq('rb_status', 'completed').execute()
                
                vendas_hoje = len(vendas_response.data or [])
                vendas_afiliados_hoje = len([v for v in (vendas_response.data or []) if v.get('rb_afiliado_id')])
                
            except Exception as e:
                print(f"❌ Erro ao obter vendas do dia: {str(e)}")

        # Calcular prêmios restantes
        premios = obter_premios_disponiveis()
        total_premios_restantes = sum(premios.values())

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


# ========== ROTAS DE SAQUE CORRIGIDAS ==========

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

    print("🚀 Iniciando Raspa Brasil com Sistema de Afiliados...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"👥 Sistema de Afiliados: ✅")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)

