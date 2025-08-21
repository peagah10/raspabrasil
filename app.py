import os
import random
import string
from datetime import datetime
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

# Inicializar cliente Supabase com tratamento de erro melhorado
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Testar conexão
        test_response = supabase.table('configuracoes').select(
            'chave'
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
        supabase.table('logs_pagamento').insert({
            'payment_id': payment_id,
            'status_anterior': status_anterior,
            'status_novo': status_novo,
            'webhook_data': webhook_data
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


def verificar_codigo_unico(codigo):
    """Verifica se o código é único no banco de dados"""
    if not supabase:
        return True
    try:
        response = supabase.table('ganhadores').select('codigo').eq(
            'codigo', codigo
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


def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração do Supabase"""
    if not supabase:
        return valor_padrao
    try:
        response = supabase.table('configuracoes').select('valor').eq(
            'chave', chave
        ).execute()
        if response.data:
            return response.data[0]['valor']
        return valor_padrao
    except Exception as e:
        print(f"❌ Erro ao obter configuração {chave}: {str(e)}")
        return valor_padrao


def atualizar_configuracao(chave, valor):
    """Atualiza valor de configuração no Supabase"""
    if not supabase:
        return False
    try:
        response = supabase.table('configuracoes').update({
            'valor': str(valor)
        }).eq('chave', chave).execute()
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
        response = supabase.table('vendas').select('quantidade').eq(
            'status', 'completed'
        ).execute()
        if response.data:
            return sum(venda['quantidade'] for venda in response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de vendas: {str(e)}")
        return 0


def obter_total_ganhadores():
    """Obtém total de ganhadores do Supabase"""
    if not supabase:
        return 0
    try:
        response = supabase.table('ganhadores').select('id').execute()
        if response.data:
            return len(response.data)
        return 0
    except Exception as e:
        print(f"❌ Erro ao obter total de ganhadores: {str(e)}")
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


@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX real via Mercado Pago"""
    data = request.json
    quantidade = data.get('quantidade', 1)
    total = quantidade * 1.00

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
                    supabase.table('vendas').insert({
                        'quantidade': quantidade,
                        'valor_total': total,
                        'payment_id': str(payment['id']),
                        'status': 'pending',
                        'ip_cliente': request.remote_addr,
                        'user_agent': request.headers.get(
                            'User-Agent', ''
                        )[:500]
                    }).execute()
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
                        # Atualizar status da venda
                        update_response = supabase.table('vendas').update({
                            'status': 'completed'
                        }).eq('payment_id', payment_id).execute()

                        if update_response.data:
                            session[payment_key] = True
                            print(
                                f"✅ Pagamento aprovado: {payment_id}"
                            )

                            # Log da mudança
                            log_payment_change(
                                payment_id, 'pending', 'completed', {
                                    'source': 'check_payment',
                                    'amount': payment.get(
                                        'transaction_amount', 0
                                    )
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
        existing = supabase.table('ganhadores').select('id').eq(
            'codigo', data['codigo']
        ).execute()
        if existing.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Código já utilizado'
            })

        response = supabase.table('ganhadores').insert({
            'codigo': data['codigo'],
            'nome': data['nome'].strip()[:255],
            'valor': data['valor'],
            'chave_pix': data['chave_pix'].strip()[:255],
            'tipo_chave': data['tipo_chave'],
            'telefone': data.get('telefone', '')[:20],
            'status_pagamento': 'pendente'
        }).execute()

        if response.data:
            print(
                f"💾 Ganhador salvo: {data['nome']} - "
                f"{data['valor']} - {data['codigo']}"
            )
            return jsonify({'sucesso': True, 'id': response.data[0]['id']})
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Erro ao inserir ganhador'
            })

    except Exception as e:
        print(f"❌ Erro ao salvar ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


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
            response = supabase.table('admins').select('*').eq('senha', senha).eq('ativo', True).execute()
            if response.data:
                admin = response.data[0]
                session['admin_logado'] = True
                session['admin_usuario'] = admin['usuario']
                
                # Atualizar último login
                supabase.table('admins').update({
                    'ultimo_login': datetime.now().isoformat()
                }).eq('id', admin['id']).execute()
                
                return jsonify({'success': True, 'message': f'Bem-vindo, {admin["nome"]}'})
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
        response = supabase.table('ganhadores').select('*').eq('codigo', codigo).execute()
        
        if response.data:
            ganhador = response.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - {ganhador["nome"]} - {ganhador["valor"]} - Status: {ganhador.get("status_pagamento", "pendente")}'
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
        response = supabase.table('ganhadores').select('*').order('data_criacao', desc=True).limit(50).execute()
        return jsonify({'premiados': response.data or []})
    except Exception as e:
        print(f"❌ Erro ao listar premiados: {str(e)}")
        return jsonify({'premiados': []})


@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema"""
    try:
        vendidas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()

        return jsonify({
            'vendidas': vendidas,
            'ganhadores': ganhadores,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS - vendidas,
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
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS,
            'supabase_conectado': False,
            'mercadopago_conectado': False,
            'sistema_ativo': True
        })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando Raspa Brasil...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
