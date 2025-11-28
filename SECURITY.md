# Security Policy

## Supported Versions

Aegis is currently in **Alpha** status. Security updates will be applied to the latest commit on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < main  | :x:                |

## Reporting a Vulnerability

We take the security of Aegis seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please Do NOT:

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before it has been addressed

### Please DO:

1. **Email the maintainer** at the email address associated with [@daveey](https://github.com/daveey)'s GitHub account
2. **Provide detailed information** including:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
3. **Allow reasonable time** for a response and fix before public disclosure

## What to Expect

- **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours
- **Updates**: We will provide regular updates on the progress of addressing the vulnerability
- **Timeline**: We aim to release a fix within 30 days for critical vulnerabilities
- **Credit**: We will credit you in the fix announcement (unless you prefer to remain anonymous)

## Security Best Practices for Users

When using Aegis, please follow these security best practices:

### API Keys and Credentials

- **Never commit** `.env` files or credentials to version control
- **Use environment variables** for all sensitive configuration
- **Rotate keys regularly** for both Asana and Anthropic APIs
- **Use restricted tokens** when possible (read-only for Asana where appropriate)

### Database Security

- **Use strong passwords** for PostgreSQL
- **Restrict database access** to localhost or trusted networks only
- **Enable SSL/TLS** for database connections in production
- **Regular backups** with encryption

### System Access

- **Run with minimal privileges** - don't run Aegis as root
- **Isolate execution environment** using containers or VMs when possible
- **Monitor logs** regularly for suspicious activity
- **Keep dependencies updated** with `uv pip install --upgrade`

### Asana Workspace

- **Use dedicated workspaces** for Aegis rather than mixing with sensitive company data
- **Review task descriptions** before letting Aegis execute them
- **Monitor agent actions** especially in autonomous mode (`aegis work-on`)
- **Set up task review processes** for critical operations

## Known Security Considerations

### Code Execution

Aegis executes code and commands as instructed by tasks in Asana. Be aware:

- **Task descriptions are trusted input** - malicious tasks can execute arbitrary code
- **Subprocess isolation is limited** - agents run with the same privileges as Aegis
- **File system access is unrestricted** - agents can read/write files as the Aegis user

**Mitigation**: Only use Aegis in trusted Asana workspaces with controlled access.

### API Keys in Logs

- Aegis uses structured logging which may include API call metadata
- **Sensitive data is not logged by default**, but review logs before sharing
- Configure log retention and access controls appropriately

### Third-Party Dependencies

- Aegis relies on external libraries (Asana SDK, Anthropic SDK, etc.)
- **Keep dependencies updated** to receive security patches
- Review dependency security advisories regularly

## Security Features

Aegis includes several security features:

- ✅ **Environment-based configuration** (no hardcoded secrets)
- ✅ **GitHub secret scanning protection** (prevents accidental commits)
- ✅ **Structured logging** (no sensitive data in logs)
- ✅ **Database credential isolation** (via environment variables)
- ✅ **CI/CD security scanning** (branch protection, status checks)

## Disclosure Policy

When a security issue is reported and fixed:

1. We will prepare a fix and test it thoroughly
2. We will release the fix to the `main` branch
3. We will publish a security advisory on GitHub
4. We will credit the reporter (unless they prefer anonymity)
5. We will update this document with lessons learned

## Questions?

If you have questions about security that don't involve reporting a vulnerability, please:

- Open a [GitHub Discussion](https://github.com/daveey/aegis/discussions)
- Check existing documentation in [docs/](docs/)

Thank you for helping keep Aegis and its users safe!
