# SpotiScript FGV

Código para coletar métricas de podcasts no Spotify for Creators, consolidar
CSV/Excel e exportar para Google Sheets e Power BI.

Esta edição pública contém apenas código e exemplos de configuração.
Foi criada com histórico independente, sem credenciais, planilhas operacionais,
dados de audiência ou histórico de commits da edição privada.

## Instalação

Requisitos: Python 3.10+, Google Chrome e Windows para os scripts PowerShell.

```powershell
git clone https://github.com/Tonksinho/spotiscript-fgv-public.git SpotiScript
cd SpotiScript
pip install -r requirements.txt
Copy-Item .env.example .env
```

Preencha o `.env` com suas próprias configurações:

- `SPOTIFY_EMAIL` e `SPOTIFY_PASSWORD`: conta autorizada no Spotify for Creators.
- `SPREADSHEET_KEY`: ID da sua própria planilha Google.
- `SERVICE_ACCOUNT_FILE`: caminho para seu JSON de service account.

Compartilhe sua planilha com a service account. O arquivo `service-account.json`,
o `.env`, os dados exportados e os perfis de navegador devem permanecer locais.
O `.gitignore` exclui esses arquivos.

## Uso

```powershell
python token_provider.py --login
python coletar.py --force
python export_para_sheets.py
python sincronizar_dashboard.py
```

Os comandos usam serviços externos e exigem configuração e permissões próprias.
A descoberta de podcasts usa a conta autenticada; o código também inclui uma
lista de podcasts FGV como fallback.

O pipeline consolida arquivos e grava as abas `Historico`, `Spotify`, `Resumo`,
`Calendario` e `DemografiaGenero`. Os dados locais ficam por padrão em
`C:\DadosPowerBI\spotify-fgv\`.

## Power BI e agendamento

Os arquivos do dashboard Power BI não estão incluídos. A abertura automática
depende de um dashboard local compatível na pasta irmã `powerbi-dashboards`.
Adapte `atualizar_dashboard.ps1` ao seu ambiente antes de usar essa integração.

Para configurar a coleta quinzenal no Windows:

```powershell
.\agendar_tarefas.ps1
```

Revise os caminhos e a configuração antes de agendar.
