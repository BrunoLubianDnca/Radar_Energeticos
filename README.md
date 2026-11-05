# Monster Radar Brasil — monitor de ofertas 473 ml

Monitor gratuito em Python + GitHub Actions com e-mail HTML e histórico. Não depende de Docker nem de API paga.

## O que faz

- Examina URLs HTTPS de páginas de produto colocadas em `sources.json`.
- Aceita **somente** produtos identificados como Monster 473 ml.
- Calcula preço por lata em unidades e kits de 6/12/24 latas, quando o título informa o tamanho.
- Envia e-mail apenas para produtos abaixo de R$ 8 por lata e **novos ou com queda em relação à última coleta válida**.
- Destaca abaixo de R$ 6,50; não conta frete como parte do preço unitário.
- Inclui foto apenas quando a página entrega um endereço HTTPS de imagem.
- Guarda histórico JSON no próprio repositório e log de erros; preserva histórico se todas as lojas falharem.

**Limites importantes:** o projeto NÃO cobre automaticamente todas as lojas brasileiras. Ele verifica as URLs cadastradas; páginas com preços carregados só por JavaScript, captcha ou anti-bot podem falhar. As 3 páginas iniciais são candidatas para validação, **não são fontes comprovadas para execução no GitHub**. Os dados de entrega para SC são apenas informativos até serem conferidos com CEP. O desconto mostrado no e-mail é a queda em relação à última observação registrada, não o desconto anunciado pela loja. Não pressupõe que fotos estejam liberadas para uso indiscriminado; usa a URL fornecida pela própria loja em e-mail transacional pessoal.

## Configuração no GitHub

1. Crie um repositório privado, por exemplo `monster-radar-brasil`, e envie os arquivos **mantendo a pasta `.github/workflows/`**.
2. Em `Settings` → `Secrets and variables` → `Actions`, crie estes **Repository secrets**:
   - `SMTP_USER`: endereço Gmail remetente.
   - `SMTP_PASSWORD`: senha de app do Gmail (NÃO senha normal da conta; requer verificação em duas etapas quando disponível).
   - `EMAIL_TO`: endereço que receberá as ofertas (pode ser o mesmo).
3. Em `Settings` → `Actions` → `General`, permita **Read and write permissions** para o `GITHUB_TOKEN`, pois o workflow registra o histórico no repositório.
4. Em `Actions` → `Monster Radar - ofertas diarias` → `Run workflow`, mantenha `dry_run=true` para testar as consultas.
5. Marque `send_test_email=true` para testar o SMTP **com uma oferta explicitamente fictícia**, mesmo quando nenhuma loja responder.
6. Para usar de verdade, cadastre URLs de páginas que mostram ofertas inequívocas e metadados Product/Offer JSON-LD ou product:price:amount. Rode o teste antes da ativação diária.
7. Só quando as fontes estiverem retornando preços válidos, execute com `dry_run=false`. Em seguida o agendamento diário às **09:20, horário de Brasília**, fica ativo no branch padrão. Execuções agendadas do GitHub podem atrasar.

## Rodar localmente

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python monitor.py --dry-run --preview
```

O arquivo `preview.html` terá valores **fictícios**, usado apenas para conferir o layout. Para não enviar e-mail ao testar com lojas reais, execute `python monitor.py --no-email` (isso atualiza o histórico).

## Personalização

Em `config.json`, altere `price_alert_brl` e `super_offer_brl`. Em `sources.json`, adicione URLs individuais de produtos (não páginas de busca nem listagens com várias ofertas agregadas) e informe a loja. Não cole dados de login ou credenciais nesses arquivos.

## Diagnóstico

Ao final da execução consulte o artefato `monster-radar-diagnostico`: `data/last-report.json` lista o número de fontes bem-sucedidas e as falhas. Se nenhuma fonte funcionar, a execução falha deliberadamente e **não manda e-mail nem apaga o histórico**.

## Observação sobre preços

Um produto de 12 unidades vendido por R$ 71,88 gera preço unitário de R$ 5,99. Um frete de R$ 30 elevaria o custo real; por isso confirme frete e CEP antes de comprar. Nem toda loja entrega em SC e a disponibilidade depende de estoque.
