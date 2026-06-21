services:
  dex:
    build: .
    image: "${DEX_IMAGE:-dex:v1.1-test}"
    container_name: dex-v1.1-test
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      - "8081:8080"
    environment:
      DEX_DATA_DIR: /data
      DEX_INBOUND_DIR: /scanner-inbox
      DEX_WATCH_INBOUND: "1"
      DEX_SCAN_INTERVAL: "5"
      DEX_SEED_DEMO: "0"
      DEX_TIMEZONE: "America/New_York"
      DEX_TCG_CAPACITY: "500"
    volumes:
      - ./storage-v1.1-test:/data
      - ./scanner-inbox-v1.1-test:/scanner-inbox
