# Mini Poker Stats Explorer

## Run

```bash
# 1) (Optional) Generate tokenized files from ClickHouse raw_hands
python backend/scripts/build_tokenized_from_clickhouse.py

# 2) Start full stack
docker compose up -d --build

# 3) Check services
docker compose ps

# 4) Check API
curl http://localhost/health
curl "http://localhost/api/v1/stats?spot=SRP&street=flop"

# 5) Open UI
# http://localhost

# 6) Smoke tests
python -m pytest -q backend/test
```

## Endpoints

- UI: `http://localhost`
- Health: `http://localhost/health`
- Stats: `http://localhost/api/v1/stats`
- Meta: `http://localhost/api/v1/meta`
