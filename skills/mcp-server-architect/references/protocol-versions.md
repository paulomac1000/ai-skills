# MCP protocol version policy

1. Record the exact protocol revision and SDK line supported by the project in a generated compatibility file.
2. Default to the latest published stable revision supported by the selected SDK.
3. Put release candidates and future revisions behind a preview build or compatibility test matrix.
4. Test negotiation or request behavior with at least one independent client.
5. Keep protocol-specific state, session, and feature assumptions outside domain services.
6. Remove legacy transport and envelope adapters only after consumer inventory proves they are unused.
