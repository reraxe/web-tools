# Migration Notes — DEX v2.5.1-live

DEX v2.5.1-live adds no migration. The expected ledger remains migrations 0001 through 0020.

An existing v2.4-live database upgrades through the already-accepted additive migration 0020 when required. An existing v2.5-live database requires no new schema work. The hotfix does not seed business rows, rewrite inventory, alter economics, or infer identities.

Normal rollback is application-image rollback to `192.168.2.92:5000/apps/dex:v2.5-live`. Do not delete migration records or restore storage merely because application startup fails.

