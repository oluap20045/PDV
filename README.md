Sistema de PDV e Controle de Estoque com Python e Docker
Este projeto é um sistema web completo para Ponto de Venda (PDV) e Controle de Estoque, desenvolvido com Python (usando o microframework Flask) e um banco de dados MySQL. Toda a aplicação é containerizada com Docker, permitindo uma instalação e execução rápida e consistente em qualquer ambiente.

Funcionalidades Principais
O sistema foi projetado para ser uma ferramenta de gestão simples e eficaz, contando com as seguintes funcionalidades:

📦 Gestão de Produtos
Cadastro de Novos Produtos: Formulário para adicionar produtos com nome, preço de venda, custo, quantidade inicial e estoque mínimo.

Edição de Produtos: Interface para atualizar todas as informações de um produto já cadastrado.

Listagem Completa: Visualização de todos os produtos com suas informações essenciais.

📈 Controle de Estoque
Visualização Inteligente: Tela dedicada para monitorar a quantidade disponível de cada item.

Alerta de Estoque Baixo: Produtos cuja quantidade atual é menor ou igual ao estoque mínimo são destacados visualmente (em amarelo) para chamar a atenção.

Busca Rápida: Filtro para encontrar produtos específicos pelo nome.

Ordenação Dinâmica: Possibilidade de ordenar a lista de produtos por nome, quantidade ou estoque mínimo com um simples clique no cabeçalho da coluna.

💰 Ponto de Venda (PDV)
Interface de Venda Rápida: Tela otimizada para adicionar produtos a um carrinho de compras.

Baixa Automática de Estoque: Ao finalizar uma venda, a quantidade dos produtos vendidos é automaticamente deduzida do estoque.

Validação de Estoque: O sistema impede a venda de produtos com quantidade insuficiente em estoque.

📊 Histórico e Análise de Vendas
Registro Detalhado: Todas as vendas são salvas com data, hora, itens, quantidades, preços e custos do momento da transação.

Cálculo de Lucratividade: A tela de histórico exibe o lucro apurado para cada item e o lucro total de cada venda.

Filtro por Período: Ferramenta de filtro para visualizar vendas realizadas entre datas específicas, com a data do dia atual como padrão.

Resumo do Período: Exibição clara do Total Vendido e do Lucro Total para o período filtrado.

Paginação: A lista de vendas é paginada para garantir a performance e a organização, mesmo com um grande volume de transações.

Tecnologias Utilizadas
Backend: Python 3.9, Flask, Flask-SQLAlchemy, Flask-Migrate

Banco de Dados: MySQL 8.0

Frontend: HTML, Bootstrap 5, JavaScript (para interatividade no PDV)

Ambiente: Docker & Docker Compose

Pré-requisitos
Antes de começar, garanta que você tenha os seguintes softwares instalados em sua máquina:

Docker

Docker Compose (geralmente já vem com o Docker Desktop)

Nota: Este projeto utiliza a sintaxe do Docker Compose V2 (ex: docker compose), que não usa hífen.

Instalação e Execução
Siga os passos abaixo para colocar o sistema no ar.

1. Clone o Repositório
Abra seu terminal, navegue até o diretório onde deseja salvar o projeto e clone o repositório:

Bash

git clone https://github.com/seu-usuario/pdv-estoque.git
cd pdv-estoque
2. Construa e Inicie os Containers
Use o Docker Compose para construir as imagens e iniciar os serviços (aplicação web e banco de dados). O comando -d (--detach) executa tudo em segundo plano, liberando seu terminal.

Bash

docker compose up -d --build
3. Crie as Tabelas no Banco de Dados
Com os containers em execução, precisamos criar a estrutura do banco de dados. Este passo só precisa ser executado uma única vez.

Bash

# (Opcional) Apenas na primeira vez que for rodar o projeto
docker compose exec web flask db init

# Gera o script de migração a partir dos seus modelos
docker compose exec web flask db migrate -m "Criação inicial do banco de dados"

# Aplica a migração e cria as tabelas
docker compose exec web flask db upgrade
4. Acesse o Sistema
Pronto! O sistema já está rodando. Abra seu navegador e acesse:
http://localhost:5000

Utilização
Comece pelo Cadastro: Acesse a aba "Cadastro de Produtos" para adicionar seus primeiros itens.

Monitore o Estoque: A aba "Controle de Estoque" mostrará seus produtos e os alertas de estoque baixo.

Realize Vendas: Vá para "PDV" para simular vendas e ver o estoque diminuir.

Analise os Resultados: A aba "Vendas Realizadas" mostrará o histórico completo, com filtros e cálculo de lucro.

Comandos Úteis do Docker Compose
Verificar o status dos containers:

Bash

docker compose ps
Ver os logs da aplicação em tempo real:

Bash

docker compose logs -f web
Parar e remover os containers:

Bash

docker compose down
Reiniciar os serviços após uma alteração no código Python:

Bash

docker compose restart

## Loja online (`/loja`)

Vitrine pública para os clientes do condomínio pedirem pelo celular. O pedido entra em **Pedidos** (selo 🛒 no menu),
reserva o estoque e é entregue/cobrado pelo PDV como qualquer pedido.

- Configuração em **Loja online** (menu): abrir/fechar, recado, WhatsApp que recebe os pedidos, chave Pix (QR Code
  "copia e cola" com o valor do pedido) e fotos/descrição/visibilidade de cada produto.
- Aparece na vitrine: produto marcado "Mostrar na loja", com preço e com estoque livre (estoque − reservas).
- Publicação: Cloudflare Tunnel (`cloudflared`) → Caddy → app. Defina `LOJA_HOST` no `.env` com o nome público:
  nesse endereço só `/loja` responde; login e sistema interno dão 404 (continuam só na rede local / ZeroTier).
- **Acessos (tráfego)** (menu Loja online → Acessos): quantas pessoas entraram, de onde vieram, aparelho, o que
  colocaram no carrinho, categorias filtradas, caminho até o pedido e horário de pico. Sem cookie e sem dado pessoal:
  cada aparelho ganha um código aleatório no `localStorage` (`app/static/js/rastreio.js` → `POST /loja/evento`).
  Robôs e prévias de link não contam; `?o=folder` no link marca a origem; `?nao_contar=1` desliga a contagem no seu
  aparelho. Eventos com mais de 400 dias são apagados sozinhos.
