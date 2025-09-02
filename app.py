import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_file
from dotenv import load_dotenv

# Inicializar Supabase
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
app.secret_key = os.getenv('SECRET_KEY', '2para1000-secret-key-2024')

# Configurações do Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', "https://ngishqxtnkgvognszyep.supabase.co")
SUPABASE_KEY = os.getenv('SUPABASE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5naXNocXh0bmtndm9nbnN6eWVwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI1OTMwNjcsImV4cCI6MjA2ODE2OTA2N30.FOksPjvS2NyO6dcZ_j0Grj3Prn9OP_udSGQwswtFBXE")

# Configurações do Mercado Pago
MP_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
sdk = None

# Configurações da aplicação
WHATSAPP_NUMERO = "5582996092684"
PREMIO_INICIAL = 1000.00
PRECO_BILHETE = 2.00

# Inicializar cliente Supabase
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado com sucesso")
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
except Exception as e:
    print(f"❌ Erro ao configurar Mercado Pago: {str(e)}")


def gerar_milhar():
    """Gera número aleatório de 4 dígitos entre 1111 e 9999"""
    return random.randint(1111, 9999)


def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração do Supabase"""
    if not supabase or not chave:
        return valor_padrao
    try:
        response = supabase.table('ml_configuracoes').select('ml_valor').eq(
            'ml_chave', chave
        ).execute()
        if response.data:
            return response.data[0]['ml_valor']
        return valor_padrao
    except Exception as e:
        print(f"❌ Erro ao obter configuração {chave}: {str(e)}")
        return valor_padrao


def atualizar_configuracao(chave, valor):
    """Atualiza valor de configuração no Supabase"""
    if not supabase or not chave:
        return False
    try:
        response = supabase.table('ml_configuracoes').update({
            'ml_valor': str(valor)
        }).eq('ml_chave', chave).execute()
        
        if not response.data:
            response = supabase.table('ml_configuracoes').insert({
                'ml_chave': chave,
                'ml_valor': str(valor)
            }).execute()
        
        return response.data is not None
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração {chave}: {str(e)}")
        return False


def obter_premio_acumulado():
    """Obtém valor do prêmio acumulado atual"""
    valor = obter_configuracao('premio_acumulado', str(PREMIO_INICIAL))
    try:
        return float(valor)
    except:
        return PREMIO_INICIAL


def atualizar_premio_acumulado(novo_valor):
    """Atualiza valor do prêmio acumulado"""
    return atualizar_configuracao('premio_acumulado', str(novo_valor))


@app.route('/')
def index():
    """Serve a página principal"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"""
        <h1>Erro ao carregar a página</h1>
        <p>Erro: {str(e)}</p>
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
    """Cria pagamento PIX via Mercado Pago"""
    data = request.json
    quantidade = data.get('quantidade', 1)
    total = quantidade * PRECO_BILHETE

    if not sdk:
        return jsonify({
            'error': 'Mercado Pago não configurado.',
            'details': 'Token do Mercado Pago necessário.'
        }), 500

    payment_data = {
        "transaction_amount": float(total),
        "description": f"2 para 1000 - {quantidade} bilhete(s)",
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@2para1000.com",
            "first_name": "Cliente",
            "last_name": "2 para 1000"
        },
        "notification_url": f"{request.url_root.rstrip('/')}/webhook/mercadopago",
        "external_reference": f"ML_{int(datetime.now().timestamp())}_{quantidade}"
    }

    try:
        payment_response = sdk.payment().create(payment_data)

        if payment_response["status"] == 201:
            payment = payment_response["response"]

            session['payment_id'] = str(payment['id'])
            session['quantidade'] = quantidade
            session['payment_created_at'] = datetime.now().isoformat()

            if supabase:
                try:
                    supabase.table('ml_vendas').insert({
                        'ml_quantidade': quantidade,
                        'ml_valor_total': total,
                        'ml_payment_id': str(payment['id']),
                        'ml_status': 'pending',
                        'ml_ip_cliente': request.remote_addr or 'unknown'
                    }).execute()
                    print(f"💾 Venda registrada: Payment {payment['id']}")
                except Exception as e:
                    print(f"❌ Erro ao salvar venda: {str(e)}")

            pix_data = payment.get('point_of_interaction', {}).get('transaction_data', {})

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
        payment_response = sdk.payment().get(str(payment_id))

        if payment_response["status"] == 200:
            payment = payment_response["response"]
            status = payment['status']

            # Se aprovado e ainda não processado, atualizar no Supabase
            payment_key = f'payment_processed_{payment_id}'
            if status == 'approved' and payment_key not in session:
                if supabase:
                    try:
                        supabase.table('ml_vendas').update({
                            'ml_status': 'completed'
                        }).eq('ml_payment_id', str(payment_id)).execute()

                        session[payment_key] = True
                        print(f"✅ Pagamento aprovado: {payment_id}")

                    except Exception as e:
                        print(f"❌ Erro ao atualizar status no Supabase: {str(e)}")

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


@app.route('/enviar_bilhete', methods=['POST'])
def enviar_bilhete():
    """Salva dados do cliente e seus bilhetes"""
    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})

    try:
        data = request.json

        campos_obrigatorios = ['nome', 'telefone', 'chave_pix', 'bilhetes']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'sucesso': False,
                    'erro': f'Campo {campo} é obrigatório'
                })

        payment_id = data.get('payment_id') or session.get('payment_id')
        if not payment_id:
            return jsonify({
                'sucesso': False,
                'erro': 'Payment ID não encontrado'
            })

        # Salvar cliente e bilhetes
        response = supabase.table('ml_clientes').insert({
            'ml_nome': data['nome'].strip()[:255],
            'ml_telefone': data['telefone'].strip()[:20],
            'ml_chave_pix': data['chave_pix'].strip()[:255],
            'ml_bilhetes': data['bilhetes'],
            'ml_payment_id': str(payment_id),
            'ml_data_sorteio': date.today().isoformat()
        }).execute()

        if response.data:
            print(f"🎫 Cliente registrado: {data['nome']} - Bilhetes: {data['bilhetes']}")
            return jsonify({'sucesso': True, 'id': response.data[0]['ml_id']})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar dados'})

    except Exception as e:
        print(f"❌ Erro ao enviar bilhete: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/resultado_sorteio')
def resultado_sorteio():
    """Obtém resultado do sorteio do dia"""
    if not supabase:
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{PREMIO_INICIAL:.2f}".replace('.', ',')
        })

    try:
        hoje = date.today().isoformat()
        
        # Buscar sorteio de hoje
        response = supabase.table('ml_sorteios').select('*').eq(
            'ml_data_sorteio', hoje
        ).execute()

        if response.data:
            sorteio = response.data[0]
            valor_acumulado = obter_premio_acumulado()
            
            return jsonify({
                'milhar_sorteada': sorteio['ml_milhar_sorteada'],
                'houve_ganhador': sorteio['ml_houve_ganhador'],
                'valor_premio': sorteio.get('ml_valor_premio', ''),
                'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
            })
        else:
            valor_acumulado = obter_premio_acumulado()
            return jsonify({
                'milhar_sorteada': None,
                'houve_ganhador': False,
                'valor_acumulado': f"{valor_acumulado:.2f}".replace('.', ',')
            })

    except Exception as e:
        print(f"❌ Erro ao obter resultado do sorteio: {str(e)}")
        return jsonify({
            'milhar_sorteada': None,
            'houve_ganhador': False,
            'valor_acumulado': f"{PREMIO_INICIAL:.2f}".replace('.', ',')
        })


@app.route('/ultimos_ganhadores')
def ultimos_ganhadores():
    """Obtém últimos ganhadores para exibir na home"""
    if not supabase:
        return jsonify({'ganhadores': []})

    try:
        response = supabase.table('ml_ganhadores').select(
            'ml_nome, ml_valor, ml_milhar_sorteada, ml_bilhete_premiado, ml_data_sorteio'
        ).order('ml_data_sorteio', desc=True).limit(6).execute()

        ganhadores = []
        for ganhador in (response.data or []):
            ganhadores.append({
                'nome': ganhador['ml_nome'][:15] + '...' if len(ganhador['ml_nome']) > 15 else ganhador['ml_nome'],
                'valor': ganhador['ml_valor'],
                'milhar': ganhador['ml_milhar_sorteada'],
                'data': datetime.fromisoformat(ganhador['ml_data_sorteio']).strftime('%d/%m/%Y')
            })

        return jsonify({'ganhadores': ganhadores})

    except Exception as e:
        print(f"❌ Erro ao obter ganhadores: {str(e)}")
        return jsonify({'ganhadores': []})


# ========== ROTAS ADMIN ==========

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
    
    return jsonify({'success': False, 'message': 'Senha incorreta'})


@app.route('/admin/sortear', methods=['POST'])
def admin_sortear():
    """Realiza sorteio diário"""
    if not session.get('admin_logado'):
        return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403

    if not supabase:
        return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})

    try:
        data = request.json
        milhar_sorteada = data.get('milhar_sorteada', '').strip()

        if not milhar_sorteada or len(milhar_sorteada) != 4 or not milhar_sorteada.isdigit():
            return jsonify({
                'sucesso': False,
                'erro': 'Milhar deve ter exatamente 4 dígitos'
            })

        hoje = date.today().isoformat()

        # Verificar se já houve sorteio hoje
        existing = supabase.table('ml_sorteios').select('ml_id').eq(
            'ml_data_sorteio', hoje
        ).execute()

        if existing.data:
            return jsonify({
                'sucesso': False,
                'erro': 'Sorteio já foi realizado hoje'
            })

        # Buscar clientes com bilhetes para hoje
        clientes_response = supabase.table('ml_clientes').select('*').eq(
            'ml_data_sorteio', hoje
        ).execute()

        houve_ganhador = False
        ganhador_data = None
        valor_premio = obter_premio_acumulado()

        # Verificar se algum cliente ganhou
        for cliente in (clientes_response.data or []):
            bilhetes = cliente['ml_bilhetes']
            if milhar_sorteada in bilhetes:
                houve_ganhador = True
                ganhador_data = cliente
                break

        if houve_ganhador:
            # Registrar ganhador
            supabase.table('ml_ganhadores').insert({
                'ml_nome': ganhador_data['ml_nome'],
                'ml_telefone': ganhador_data['ml_telefone'],
                'ml_chave_pix': ganhador_data['ml_chave_pix'],
                'ml_bilhete_premiado': milhar_sorteada,
                'ml_milhar_sorteada': milhar_sorteada,
                'ml_valor': f"R$ {valor_premio:.2f}".replace('.', ','),
                'ml_data_sorteio': hoje,
                'ml_status_pagamento': 'pendente'
            }).execute()

            # Resetar prêmio para valor inicial
            atualizar_premio_acumulado(PREMIO_INICIAL)
            novo_valor_acumulado = PREMIO_INICIAL

            print(f"🏆 GANHADOR! {ganhador_data['ml_nome']} - Bilhete: {milhar_sorteada} - Prêmio: R$ {valor_premio:.2f}")

        else:
            # Acumular prêmio
            novo_valor_acumulado = valor_premio + PREMIO_INICIAL
            atualizar_premio_acumulado(novo_valor_acumulado)

            print(f"💰 Prêmio acumulado! Novo valor: R$ {novo_valor_acumulado:.2f}")

        # Registrar sorteio
        supabase.table('ml_sorteios').insert({
            'ml_data_sorteio': hoje,
            'ml_milhar_sorteada': milhar_sorteada,
            'ml_houve_ganhador': houve_ganhador,
            'ml_valor_premio': f"R$ {valor_premio:.2f}".replace('.', ',') if houve_ganhador else '',
            'ml_novo_valor_acumulado': f"R$ {novo_valor_acumulado:.2f}".replace('.', ',')
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
        print(f"❌ Erro ao realizar sorteio: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)})


@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema"""
    try:
        stats = {
            'bilhetes_vendidos': 0,
            'total_ganhadores': 0,
            'premio_atual': f"{obter_premio_acumulado():.2f}".replace('.', ',')
        }

        if supabase:
            try:
                # Contar bilhetes vendidos (soma das quantidades)
                vendas_response = supabase.table('ml_vendas').select('ml_quantidade').eq(
                    'ml_status', 'completed'
                ).execute()
                
                if vendas_response.data:
                    stats['bilhetes_vendidos'] = sum(v['ml_quantidade'] for v in vendas_response.data)

                # Contar ganhadores
                ganhadores_response = supabase.table('ml_ganhadores').select('ml_id').execute()
                if ganhadores_response.data:
                    stats['total_ganhadores'] = len(ganhadores_response.data)

            except Exception as e:
                print(f"❌ Erro ao obter estatísticas: {str(e)}")

        return jsonify(stats)

    except Exception as e:
        print(f"❌ Erro geral nas estatísticas: {str(e)}")
        return jsonify({
            'bilhetes_vendidos': 0,
            'total_ganhadores': 0,
            'premio_atual': f"{PREMIO_INICIAL:.2f}".replace('.', ',')
        })


@app.route('/admin/bilhetes')
def admin_bilhetes():
    """Lista bilhetes vendidos hoje"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})

    if not supabase:
        return jsonify({'bilhetes': []})

    try:
        hoje = date.today().isoformat()
        response = supabase.table('ml_clientes').select('*').eq(
            'ml_data_sorteio', hoje
        ).order('ml_data_criacao', desc=True).execute()

        return jsonify({'bilhetes': response.data or []})

    except Exception as e:
        print(f"❌ Erro ao listar bilhetes: {str(e)}")
        return jsonify({'bilhetes': []})


@app.route('/admin/ganhadores')
def admin_ganhadores():
    """Lista ganhadores"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})

    if not supabase:
        return jsonify({'ganhadores': []})

    try:
        response = supabase.table('ml_ganhadores').select('*').order(
            'ml_data_sorteio', desc=True
        ).execute()

        return jsonify({'ganhadores': response.data or []})

    except Exception as e:
        print(f"❌ Erro ao listar ganhadores: {str(e)}")
        return jsonify({'ganhadores': []})


@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago"""
    try:
        data = request.json
        print(f"📬 Webhook recebido: {data}")
        
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            if payment_id and supabase and sdk:
                try:
                    payment_response = sdk.payment().get(payment_id)
                    if payment_response["status"] == 200:
                        payment = payment_response["response"]
                        status = payment['status']
                        
                        supabase.table('ml_vendas').update({
                            'ml_status': 'completed' if status == 'approved' else status
                        }).eq('ml_payment_id', str(payment_id)).execute()
                        
                        print(f"📊 Status atualizado via webhook: {payment_id} -> {status}")
                        
                except Exception as e:
                    print(f"❌ Erro ao processar webhook: {str(e)}")
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"❌ Erro no webhook: {str(e)}")
        return jsonify({'error': 'webhook_error'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando 2 PARA 1000 - Sistema de Bilhetes Premiados...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"🎯 Sistema: Bilhetes de Milhar com Sorteio Diário")
    print(f"💰 Preço por bilhete: R$ {PRECO_BILHETE:.2f}")
    print(f"🏆 Prêmio inicial: R$ {PREMIO_INICIAL:.2f}")
    print(f"🕕 Sorteio: Diário às 18h baseado na Lotep/PB")
    print(f"📊 Funcionalidades:")
    print(f"   - ✅ Compra de bilhetes com números aleatórios")
    print(f"   - ✅ Formulário de dados do cliente")
    print(f"   - ✅ Sistema de sorteio diário")
    print(f"   - ✅ Acúmulo de prêmios")
    print(f"   - ✅ Área admin completa")
    print(f"   - ✅ Histórico de ganhadores")
    print(f"   - ✅ Pagamento via PIX")
    print(f"   - ✅ Sistema 100% funcional!")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
