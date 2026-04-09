# Página de confirmação (GitHub Pages)

Este diretório contém a página estática para confirmação de e-mail.

## Publicar no GitHub Pages

1. Suba este diretório no repositório (pasta `docs`).
2. No GitHub: **Settings → Pages**.
3. Em **Build and deployment**:
   - **Source**: Deploy from a branch
   - **Branch**: `main` (ou a branch que você usa)
   - **Folder**: `/docs`
4. Salve e aguarde publicar.

URL final (exemplo):

`https://SEU-USUARIO.github.io/SEU-REPO/`

## Configurar no Supabase

No painel do Supabase:

- **Authentication → URL Configuration**
  - **Site URL**: `https://SEU-USUARIO.github.io/SEU-REPO/`
  - **Redirect URLs**: adicionar também `https://SEU-USUARIO.github.io/SEU-REPO/`

Depois disso, os e-mails de confirmação vão abrir esta página em vez de `localhost`.
