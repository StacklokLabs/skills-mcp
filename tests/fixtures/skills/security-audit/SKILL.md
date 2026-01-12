---
name: security-audit
description: Identify security vulnerabilities and recommend fixes based on OWASP guidelines
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: security
allowed-tools: Read Grep Glob
---

# Security Audit Skill

Systematically identify security vulnerabilities in code using OWASP Top 10 and security best practices.

## OWASP Top 10 (2021) Checklist

### A01: Broken Access Control
- [ ] Authorization checks on all protected resources
- [ ] Server-side enforcement (not just client-side)
- [ ] Deny by default
- [ ] Rate limiting on sensitive operations
- [ ] CORS properly configured

**Look for:**
```python
# BAD: No authorization check
@app.route('/admin/users')
def list_users():
    return User.query.all()

# GOOD: Authorization enforced
@app.route('/admin/users')
@requires_role('admin')
def list_users():
    return User.query.all()
```

### A02: Cryptographic Failures
- [ ] No hardcoded secrets or keys
- [ ] Strong algorithms (AES-256, SHA-256+, bcrypt)
- [ ] TLS for data in transit
- [ ] Encryption for sensitive data at rest
- [ ] Proper key management

**Look for:**
- `MD5`, `SHA1` for passwords (weak)
- Hardcoded API keys, passwords
- HTTP instead of HTTPS
- Weak random number generation

### A03: Injection
- [ ] Parameterized queries for SQL
- [ ] Input validation and sanitization
- [ ] Output encoding for XSS prevention
- [ ] Command injection protection

**Look for:**
```python
# BAD: SQL Injection
query = f"SELECT * FROM users WHERE id = {user_id}"

# GOOD: Parameterized
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))
```

### A04: Insecure Design
- [ ] Threat modeling performed
- [ ] Security requirements defined
- [ ] Secure design patterns used
- [ ] Defense in depth

### A05: Security Misconfiguration
- [ ] Debug mode disabled in production
- [ ] Default credentials changed
- [ ] Unnecessary features disabled
- [ ] Security headers configured
- [ ] Error messages don't leak info

**Check for:**
```python
# BAD
DEBUG = True
SECRET_KEY = "default-secret-key"

# GOOD
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")  # Required, no default
```

### A06: Vulnerable Components
- [ ] Dependencies up to date
- [ ] Known vulnerabilities patched
- [ ] Only necessary dependencies included
- [ ] Components from trusted sources

### A07: Authentication Failures
- [ ] Strong password requirements
- [ ] Account lockout after failed attempts
- [ ] Secure session management
- [ ] MFA where appropriate
- [ ] Secure password storage (bcrypt, argon2)

### A08: Data Integrity Failures
- [ ] Verify signatures on updates
- [ ] Validate data integrity
- [ ] Secure CI/CD pipeline
- [ ] Code signing

### A09: Logging & Monitoring
- [ ] Log security events
- [ ] Don't log sensitive data
- [ ] Alerting on suspicious activity
- [ ] Log integrity protection

**Look for:**
```python
# BAD: Logging sensitive data
logger.info(f"User login: {username}, password: {password}")

# GOOD: Log event, not sensitive data
logger.info(f"User login attempt: {username}")
```

### A10: SSRF (Server-Side Request Forgery)
- [ ] Validate/sanitize user-supplied URLs
- [ ] Allowlist for allowed destinations
- [ ] Block requests to internal resources
- [ ] Disable redirects or validate them

## Language-Specific Patterns

### Python
```python
# Dangerous: eval, exec, pickle.loads
eval(user_input)  # Code injection
pickle.loads(data)  # Arbitrary code execution
subprocess.shell=True  # Command injection

# Safe alternatives
ast.literal_eval(user_input)  # For literals only
json.loads(data)  # For data serialization
subprocess.run([cmd, arg], shell=False)
```

### JavaScript
```javascript
// Dangerous
innerHTML = userInput  // XSS
eval(userInput)  // Code injection
new Function(userInput)  // Code injection

// Safe
textContent = userInput
// Use sanitization libraries for HTML
```

### SQL
```sql
-- Always use parameterized queries
-- Never concatenate user input
```

## Security Headers

Ensure these headers are set:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'
X-XSS-Protection: 1; mode=block
```

## Audit Report Format

```markdown
## Security Finding

**Severity**: Critical/High/Medium/Low/Info
**Category**: OWASP A0X - Name
**Location**: file.py:line

### Description
[What the vulnerability is]

### Impact
[What an attacker could do]

### Recommendation
[How to fix it]

### Code Example
[Before/After code snippets]
```
