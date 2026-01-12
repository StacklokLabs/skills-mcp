---
name: api-design
description: Design RESTful APIs following best practices for consistency, usability, and scalability
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: architecture
allowed-tools: Read Write
---

# RESTful API Design Skill

Design APIs that are intuitive, consistent, and maintainable.

## URL Structure

### Resource Naming
- Use **nouns**, not verbs: `/users` not `/getUsers`
- Use **plural** forms: `/users`, `/orders`, `/products`
- Use **lowercase** with hyphens: `/user-profiles`
- Keep URLs **flat** when possible

### Hierarchy
```
/users                     # Collection
/users/{id}                # Single resource
/users/{id}/orders         # Sub-collection
/users/{id}/orders/{id}    # Nested resource
```

### Query Parameters
```
/users?status=active       # Filtering
/users?sort=created_at     # Sorting
/users?page=2&limit=20     # Pagination
/users?fields=id,name      # Sparse fieldsets
```

## HTTP Methods

| Method | Purpose | Idempotent | Safe |
|--------|---------|------------|------|
| GET | Retrieve resource(s) | Yes | Yes |
| POST | Create resource | No | No |
| PUT | Replace resource | Yes | No |
| PATCH | Partial update | Yes | No |
| DELETE | Remove resource | Yes | No |

### Method Usage Examples
```
GET    /users          # List users
POST   /users          # Create user
GET    /users/123      # Get user 123
PUT    /users/123      # Replace user 123
PATCH  /users/123      # Update user 123
DELETE /users/123      # Delete user 123
```

## Status Codes

### Success (2xx)
| Code | Use Case |
|------|----------|
| 200 | GET success, PUT/PATCH success with body |
| 201 | POST created (include Location header) |
| 204 | DELETE success, PUT/PATCH success no body |

### Client Errors (4xx)
| Code | Use Case |
|------|----------|
| 400 | Malformed request, validation error |
| 401 | Missing/invalid authentication |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate, state conflict) |
| 422 | Validation failed (semantic error) |
| 429 | Rate limit exceeded |

### Server Errors (5xx)
| Code | Use Case |
|------|----------|
| 500 | Unexpected server error |
| 502 | Bad gateway |
| 503 | Service unavailable |

## Request/Response Format

### Request Body (POST/PUT/PATCH)
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "role": "admin"
}
```

### Success Response
```json
{
  "data": {
    "id": "123",
    "type": "user",
    "attributes": {
      "name": "John Doe",
      "email": "john@example.com"
    }
  }
}
```

### Collection Response
```json
{
  "data": [...],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20
  },
  "links": {
    "self": "/users?page=1",
    "next": "/users?page=2",
    "last": "/users?page=5"
  }
}
```

### Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  }
}
```

## Versioning

### URL Path (Recommended)
```
/v1/users
/v2/users
```

### Header
```
Accept: application/vnd.api+json; version=1
```

## Authentication

### Bearer Token
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### API Key
```
X-API-Key: your-api-key
# Or in query param (less secure)
/users?api_key=your-api-key
```

## Pagination Patterns

### Offset-based
```
GET /users?offset=20&limit=10
```

### Cursor-based (for large datasets)
```
GET /users?cursor=eyJpZCI6MTIzfQ&limit=10
```

## Filtering & Sorting

### Filtering
```
GET /users?status=active
GET /users?created_after=2024-01-01
GET /users?role=admin,user  # Multiple values
```

### Sorting
```
GET /users?sort=created_at       # Ascending
GET /users?sort=-created_at      # Descending
GET /users?sort=name,-created_at # Multiple fields
```

## Best Practices

1. **Use consistent naming**: Pick a convention and stick to it
2. **Version from day one**: `/v1/` prefix
3. **Return useful errors**: Include error codes and messages
4. **Support filtering**: Let clients request only what they need
5. **Implement pagination**: Never return unbounded lists
6. **Use proper status codes**: Not just 200 and 500
7. **Document everything**: OpenAPI/Swagger spec
8. **Rate limit**: Protect your API from abuse
9. **Cache appropriately**: Use ETags, Cache-Control
10. **Be consistent**: Same patterns across all endpoints
