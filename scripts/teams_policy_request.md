# Solicitação — Política de Acesso para App LMS no Teams

## Motivo

A plataforma LMS precisa criar reuniões do Teams automaticamente (aulas síncronas).
A app Azure `d8db36c7-bdda-4713-9048-59835c25e9da` já tem as permissões de Graph API
aprovadas, mas o Teams exige uma **Application Access Policy** extra para permitir
que apps criem reuniões em nome de usuários.

## O que fazer

Alguém com permissão de **Teams Admin** (ou Global Admin) precisa executar os
3 comandos abaixo no **PowerShell do Teams** (Cloud Shell do Azure ou
Teams PowerShell Module local):

```powershell
# 1. Conectar ao Teams
Connect-MicrosoftTeams

# 2. Criar a política que autoriza a app
New-CsApplicationAccessPolicy -Identity "LMS-Meeting-Policy" -AppIds "d8db36c7-bdda-4713-9048-59835c25e9da" -Description "Permite LMS criar reunioes Teams"

# 3. Conceder a política ao usuário organizador
Grant-CsApplicationAccessPolicy -PolicyName "LMS-Meeting-Policy" -Identity "gabriel.cicotoste@grupoge21.com"
```

## Informações da App

- **App ID:** `d8db36c7-bdda-4713-9048-59835c25e9da`
- **Tenant ID:** `dddcb390-7979-49ac-90d7-b614eec878d0`
- **Permissão necessária:** `OnlineMeetings.ReadWrite.All` (já concedida)
- **Usuário organizador:** `gabriel.cicotoste@grupoge21.com`
