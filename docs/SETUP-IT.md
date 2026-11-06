# Microsoft setup for district IT

The app needs one Microsoft Entra ID app registration for sign-in and email. Make a second
registration for testing if you prefer to keep test and production apart. Microsoft renames
portal menus often, so if a label below doesn't match, search the Entra admin center for it.

## 1. App registration (sign-in)

1. Entra admin center > Applications > App registrations > New registration.
2. Name: `Service Hours`. Supported account types: **this organizational directory only** (single tenant).
3. Redirect URI, platform **Web**: `https://<your-site>/accounts/microsoft/callback/`.
   For local testing, also add `http://localhost:8000/accounts/microsoft/callback/`.
4. Certificates & secrets > New client secret. Copy the value right away. Note the expiry date
   and put a reminder on the calendar, because sign-in breaks when the secret expires.
5. API permissions: Microsoft Graph > Delegated > `User.Read` (usually there by default).
6. Give the app these values as environment variables:

| Variable | Where to find it |
| --- | --- |
| `MS_TENANT_ID` | Overview > Directory (tenant) ID |
| `MS_CLIENT_ID` | Overview > Application (client) ID |
| `MS_CLIENT_SECRET` | The secret value from step 4 |

The app accepts only accounts from `MS_TENANT_ID`. People from other organizations are refused.

## 2. Roles

- Everyone who signs in starts as a **student**.
- Emails in `TEACHER_EMAILS` become teachers and emails in `ADMIN_EMAILS` become admins (comma
  separated). Admins can also change roles in the admin site at `/admin/`.
- Assign each teacher's grade level under Admin > Users > the teacher > Grade assignments.
- Students choose their graduation year the first time they sign in. Teachers or admins can
  correct it in the admin site.

## 3. Sending email from a school mailbox (Microsoft Graph)

1. Create a shared mailbox, for example `servicehours@yourschool.org`.
2. In the same app registration, under API permissions, add Microsoft Graph > **Application** >
   `Mail.Send`, then choose **Grant admin consent**.
3. **Limit it to that one mailbox.** Without this step, the app could send as anyone in the
   district. In Exchange Online PowerShell, use an application access policy (older method) or
   RBAC for Applications (the newer method Microsoft recommends). For example:

   ```powershell
   New-ApplicationAccessPolicy -AppId <MS_CLIENT_ID> `
     -PolicyScopeGroupId servicehours-senders@yourschool.org `
     -AccessRight RestrictAccess -Description "Service Hours app can send only as this mailbox"
   ```

   Here `servicehours-senders` is a mail-enabled security group that contains only the mailbox.
4. Set `EMAIL_PROVIDER=graph`, `GRAPH_SENDER_MAILBOX=servicehours@yourschool.org`, and
   `DEFAULT_FROM_EMAIL=servicehours@yourschool.org`.

Supervisor replies go to the student, because the app sets Reply-To to the student's address.

## 4. Email filtering

Safe Links and other scanners open links automatically. The app is built for this: opening a
link never approves anything. If supervisor emails go to junk, ask the email team to make sure
SPF, DKIM, and DMARC are set for the sending domain.
