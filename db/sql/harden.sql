-- Per-database hardening. Run connected to the redshadow database, as a superuser.
-- Used by db/init/10-roles.sh (first start) and scripts/restore.sh (fresh DB before restore).
-- redshadow_owner runs migrations (DDL). redshadow_app is DML-only: no DDL, no CREATE.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO redshadow_owner;
GRANT USAGE ON SCHEMA public TO redshadow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE redshadow_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO redshadow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE redshadow_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO redshadow_app;
