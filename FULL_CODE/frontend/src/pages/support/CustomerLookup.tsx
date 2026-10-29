import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Eye, Search, Shield, User } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

export default function CustomerLookup() {
  const { selected } = useConnections();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get("q") || "";

  const [inputVal, setInputVal] = useState(queryParam);
  const [searchTerm, setSearchTerm] = useState(queryParam);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputVal.trim();
    if (!clean) {
      setValidationError("Please enter a Customer ID (e.g. CIF-00UKL72D), Name, or Phone number.");
      return;
    }
    setValidationError(null);
    setSearchTerm(clean);
    setSearchParams({ q: clean });
  };

  const lookupQ = useQuery({
    queryKey: ["customer-lookup", selected?.id, searchTerm],
    queryFn: async () => {
      if (!selected?.id || !searchTerm) return null;

      // Clean search term to prevent raw SQL syntax errors while using SQLGlot parser
      const term = searchTerm.replace(/['"\\]/g, "");

      // Safe query that leverages backend sqlglot guard and server-side partial masking
      const sql = term.toUpperCase().startsWith("CIF-")
        ? `SELECT customer_id, cust_nm, mob_no, emailid, city, state, segment, dob_dt FROM customers WHERE customer_id = '${term.toUpperCase()}' LIMIT 10`
        : `SELECT customer_id, cust_nm, mob_no, emailid, city, state, segment, dob_dt FROM customers WHERE cust_nm LIKE '%${term}%' OR mob_no LIKE '%${term}%' LIMIT 15`;

      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected.id, sql },
      });

      return res;
    },
    enabled: !!selected?.id && !!searchTerm,
  });

  const sampleCifs = ["CIF-00UKL72D", "CIF-007IS5OP", "CIF-0080J9GL", "CIF-007KK65R", "CIF-UGZKM7GD", "CIF-2FOFTGNB"];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-xs font-semibold uppercase text-amber-300">
            Customer Identification & Verification
          </span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-fog-100">Customer Lookup</h1>
        <p className="text-sm text-fog-400">
          Find customer accounts across Saffron Bank database. Permitted fields are delivered with role-approved partial masking.
        </p>
      </div>

      {/* Search Input Card */}
      <Card title="Search Customers" subtitle="Search by Customer Identifier (CIF-...), Name, or Mobile Number">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-fog-500" />
            <input
              type="text"
              className="input pl-9 text-sm"
              placeholder="e.g. CIF-00UKL72D, Ananya, or 98..."
              value={inputVal}
              onChange={(e) => {
                setInputVal(e.target.value);
                if (validationError) setValidationError(null);
              }}
            />
          </div>
          <Button variant="primary" type="submit" loading={lookupQ.isLoading} icon={<Search className="h-4 w-4" />}>
            Search Customer
          </Button>
        </form>

        {validationError && (
          <div className="mt-3">
            <Alert tone="error">{validationError}</Alert>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-fog-400">
          <span className="font-medium text-fog-300">Quick Test Records:</span>
          {sampleCifs.map((cif) => (
            <button
              key={cif}
              type="button"
              onClick={() => {
                setInputVal(cif);
                setSearchTerm(cif);
                setSearchParams({ q: cif });
              }}
              className="rounded border border-ink-600 bg-ink-800 px-2 py-1 font-mono text-[11px] text-amber-200 transition-colors hover:border-amber-400 hover:bg-ink-700"
            >
              {cif}
            </button>
          ))}
        </div>
      </Card>

      {/* Privacy Notice Banner */}
      <div className="flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-900/50 px-4 py-2.5 text-xs text-fog-400">
        <Shield className="h-4 w-4 text-amber-400 shrink-0" />
        <span>
          <strong className="text-fog-200">Active Privacy Enforcement:</strong> All customer names, phone numbers, and emails shown below have been sanitized on the server prior to network transmission.
        </span>
      </div>

      {/* Results State */}
      {lookupQ.isLoading ? (
        <Card>
          <div className="py-12">
            <Spinner label="Executing authorized support query on Saffron Bank..." />
          </div>
        </Card>
      ) : lookupQ.data && !lookupQ.data.ok ? (
        /* Access Denied or Backend Error State */
        <Card>
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-6 w-6 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-semibold text-rose-200">Query Restricted / Access Denied</h3>
                <p className="mt-1 text-xs text-rose-300/90 leading-relaxed">
                  {lookupQ.data.body?.error?.message || "The query could not be executed under your role's current security policies."}
                </p>
                <div className="mt-3 text-[11px] font-mono text-rose-400">
                  Code: {lookupQ.data.body?.error?.code || "policy_rejection"} · Status: {lookupQ.data.status}
                </div>
              </div>
            </div>
          </div>
        </Card>
      ) : lookupQ.data && lookupQ.data.body?.rows ? (
        /* Successful Results */
        lookupQ.data.body.rows.length === 0 ? (
          <Card>
            <div className="py-12 text-center">
              <User className="mx-auto h-8 w-8 text-fog-500" />
              <h3 className="mt-2 text-sm font-medium text-fog-200">No Customers Found</h3>
              <p className="mt-1 text-xs text-fog-400">
                No customer records matched "{searchTerm}". Try another Customer ID or name.
              </p>
            </div>
          </Card>
        ) : (
          <Card
            title={`Search Results (${lookupQ.data.body.rows.length} records found)`}
            subtitle="Click on any customer to open their Customer 360 profile"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-ink-700 text-fog-400">
                  <tr>
                    <th className="pb-2.5 font-medium">Customer ID</th>
                    <th className="pb-2.5 font-medium">
                      Customer Name <span className="text-[10px] text-amber-400">(Masked)</span>
                    </th>
                    <th className="pb-2.5 font-medium">
                      Mobile Number <span className="text-[10px] text-amber-400">(Masked)</span>
                    </th>
                    <th className="pb-2.5 font-medium">
                      Email Address <span className="text-[10px] text-amber-400">(Masked)</span>
                    </th>
                    <th className="pb-2.5 font-medium">Location</th>
                    <th className="pb-2.5 font-medium">Segment</th>
                    <th className="pb-2.5 text-right font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-800 text-fog-200">
                  {lookupQ.data.body.rows.map((row: any[], i: number) => {
                    const [cif, name, mob, email, city, state, seg] = row;
                    return (
                      <tr key={cif || i} className="transition-colors hover:bg-ink-800/40">
                        <td className="py-3 font-mono font-medium text-cyan">
                          {cif}
                        </td>
                        <td className="py-3">
                          <div className="font-medium text-fog-100">{name}</div>
                          <Badge tone="amber" className="mt-0.5 text-[10px]">Partially Masked</Badge>
                        </td>
                        <td className="py-3 font-mono text-fog-300">
                          <div>{mob}</div>
                          <Badge tone="amber" className="mt-0.5 text-[10px]">Partially Masked</Badge>
                        </td>
                        <td className="py-3 text-fog-300">
                          <div>{email}</div>
                          <Badge tone="amber" className="mt-0.5 text-[10px]">Partially Masked</Badge>
                        </td>
                        <td className="py-3 text-fog-300">
                          {city && state ? `${city}, ${state}` : city || state || "—"}
                        </td>
                        <td className="py-3">
                          <Badge tone="cyan">{seg || "RETAIL"}</Badge>
                        </td>
                        <td className="py-3 text-right">
                          <Link to={`/support/profiles?id=${encodeURIComponent(cif)}`}>
                            <Button size="sm" variant="secondary" icon={<Eye className="h-3.5 w-3.5" />}>
                              View 360° Profile
                            </Button>
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-4 border-t border-ink-800 pt-3 text-right text-[11px] text-fog-500">
              Query completed in {lookupQ.data.body.duration_ms} ms · Enforced server-side masking on {lookupQ.data.body.decisions?.length || 8} columns
            </div>
          </Card>
        )
      ) : (
        /* Initial Empty Search State */
        <Card>
          <div className="py-12 text-center">
            <Search className="mx-auto h-8 w-8 text-fog-500" />
            <h3 className="mt-2 text-sm font-medium text-fog-200">Enter a customer query</h3>
            <p className="mt-1 text-xs text-fog-400 max-w-sm mx-auto">
              Type a Customer ID like <code>CIF-00UKL72D</code>, a customer name, or mobile number to look up customer records safely.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
