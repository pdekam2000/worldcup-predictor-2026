import React, { useEffect, useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { buildApiUrl } from "@/lib/config";
import {
  APP_VERSION,
  BUILD_DATE,
  BUILD_LABEL,
  COMMIT_HASH,
  FRONTEND_VERSION,
  frontendDisplayFull,
  frontendDisplayShort,
} from "@/lib/appVersion";
import { isAdminUser, isOwnerUser } from "@/lib/roles";

async function fetchBackendVersion() {
  const response = await fetch(buildApiUrl("/api/version"));
  if (!response.ok) {
    throw new Error(`version ${response.status}`);
  }
  return response.json();
}

function envShortFromPayload(payload) {
  return payload?.environment_short || payload?.environment || "dev";
}

export default function AppVersionBadge({ user, className = "" }) {
  const [backend, setBackend] = useState(null);
  const [error, setError] = useState(null);

  const privileged = isOwnerUser(user) || isAdminUser(user);

  useEffect(() => {
    let cancelled = false;
    fetchBackendVersion()
      .then((data) => {
        if (!cancelled) {
          setBackend(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setBackend(null);
          setError(err instanceof Error ? err.message : "unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const envShort = envShortFromPayload(backend);
  const shortLabel = backend?.display_short || frontendDisplayShort();
  const fullLabel = backend?.display_full || frontendDisplayFull(envShort);

  const detailRows = useMemo(
    () => [
      { label: "Frontend", value: `v${FRONTEND_VERSION}` },
      { label: "Backend", value: backend?.app_version ? `v${backend.app_version}` : "—" },
      { label: "Backend commit", value: backend?.backend_commit || backend?.commit || COMMIT_HASH },
      { label: "Frontend commit", value: backend?.frontend_commit || COMMIT_HASH },
      { label: "DB schema", value: backend?.database_schema || backend?.sqlite_schema_version || "—" },
      { label: "Migration", value: backend?.migration_version || backend?.postgres_migration || "—" },
      { label: "Build label", value: backend?.build_label || BUILD_LABEL },
      { label: "Build date", value: backend?.build_date || BUILD_DATE },
      { label: "Environment", value: backend?.environment || "—" },
      { label: "API", value: backend?.api_version ? `v${backend.api_version}` : "—" },
    ],
    [backend]
  );

  const badgeClass =
    "inline-flex items-center rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 font-mono text-[10px] text-[#94A3B8] hover:border-[#00E676]/30 hover:text-[#00E676] transition-colors max-w-[min(100vw-8rem,20rem)]";

  const badgeBody = (
    <>
      <span className="sm:hidden truncate">{shortLabel}</span>
      <span className="hidden sm:inline truncate">{fullLabel}</span>
    </>
  );

  if (privileged) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={`${badgeClass} ${className}`}
            title={error ? `Version API: ${error}` : "Deploy version details"}
            aria-label="Application version details"
          >
            {badgeBody}
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          className="w-80 border-white/10 bg-[#101827] text-[#F8FAFC] p-4"
        >
          <p className="text-xs font-semibold text-[#00E676] mb-3 uppercase tracking-wider">
            Deploy version
          </p>
          <dl className="space-y-2 text-xs">
            {detailRows.map((row) => (
              <div key={row.label} className="flex justify-between gap-3">
                <dt className="text-[#64748B]">{row.label}</dt>
                <dd className="font-mono text-[#F8FAFC] text-right break-all">{row.value}</dd>
              </div>
            ))}
          </dl>
          {error && (
            <p className="mt-3 text-[10px] text-[#FFD166]">Backend version API: {error}</p>
          )}
          {!error && backend?.commit && backend.commit !== COMMIT_HASH && (
            <p className="mt-3 text-[10px] text-[#FFD166]">
              Frontend/backend commit mismatch — redeploy or hard-refresh.
            </p>
          )}
        </PopoverContent>
      </Popover>
    );
  }

  return (
    <span
      className={`${badgeClass} cursor-default ${className}`}
      title={shortLabel}
      aria-label={`Application version ${shortLabel}`}
    >
      {badgeBody}
    </span>
  );
}
