# Use uma imagem base oficial do Python
FROM python:3.9-slim

# Defina o diretório de trabalho dentro do container
WORKDIR /app

# Copie o arquivo de dependências e instale-as
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Copie o resto do código da aplicação para o diretório de trabalho
COPY . .

# Exponha a porta que a aplicação Flask irá rodar
EXPOSE 5000

# Comando para rodar a aplicação quando o container iniciar
CMD ["flask", "run", "--host=0.0.0.0"]
