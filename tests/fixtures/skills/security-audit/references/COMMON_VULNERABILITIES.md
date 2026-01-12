# Common Vulnerabilities Quick Reference

## Injection Attacks

### SQL Injection
```python
# Vulnerable
db.execute(f"SELECT * FROM users WHERE id = {id}")

# Fixed
db.execute("SELECT * FROM users WHERE id = ?", (id,))
```

### Command Injection
```python
# Vulnerable
os.system(f"ping {host}")

# Fixed
subprocess.run(["ping", host], shell=False)
```

### XSS (Cross-Site Scripting)
```javascript
// Vulnerable
element.innerHTML = userInput

// Fixed
element.textContent = userInput
// Or use DOMPurify for HTML
```

## Authentication Issues

### Weak Password Storage
```python
# Vulnerable
password_hash = hashlib.md5(password).hexdigest()

# Fixed
password_hash = bcrypt.hashpw(password, bcrypt.gensalt())
```

### Session Fixation
- Regenerate session ID after login
- Use secure, httpOnly cookies
- Set appropriate expiration

## Sensitive Data Exposure

### Hardcoded Secrets
```python
# Vulnerable
API_KEY = "sk-1234567890abcdef"

# Fixed
API_KEY = os.environ.get("API_KEY")
```

### Logging Sensitive Data
```python
# Vulnerable
logger.info(f"Payment processed: card={card_number}")

# Fixed
logger.info(f"Payment processed: card=****{card_number[-4:]}")
```

## Path Traversal

```python
# Vulnerable
file_path = f"/uploads/{filename}"

# Fixed
safe_name = secure_filename(filename)
file_path = os.path.join("/uploads", safe_name)
# Also check that final path is within allowed directory
```
