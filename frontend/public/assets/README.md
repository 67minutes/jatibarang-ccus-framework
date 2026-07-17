# Static asset policy

The workbench ships no terrain, reservoir model, launch-pad bank, request, or
screening result. It opens as a blank slate and obtains engineering inputs only
through an explicit New Study import or an opened study memo.

Runtime imports are registered by hash under the backend's ignored
`data/imports/` area. Scientific test fixtures remain under `frontend/src/test/`
and are never fetched by the application at startup.
