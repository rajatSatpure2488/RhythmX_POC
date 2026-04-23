# MediSync — DrChrono API Reference

## Authentication
- OAuth 2.0 Authorization Code flow
- Manual bearer token fallback
- Token endpoint: https://drchrono.com/o/token/

## Base URL
https://app.drchrono.com/api

## Key Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | /patients | Search/list patients |
| POST | /patients | Create patient |
| PATCH | /patients/{id} | Update patient |
| GET | /medications | List medications |
| POST | /medications | Create medication |
| ... | ... | (fill per resource) |

## Rate Limits
- 500 requests/day
- 29 requests/minute

## TODO: Fill all 13 resource endpoint details
