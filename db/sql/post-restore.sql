-- Re-applies privilege restrictions that default privileges would otherwise widen while
-- pg_restore recreates tables. Run after every restore. Add new append-only tables here.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM redshadow_app;
