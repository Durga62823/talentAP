import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Eye, Search, User } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MaskBadge, PurposeBanner, decisionOf } from "../../components/PurposeBinding";
import { Alert, Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";
import { purposeHeaders, usePurposeBinding } from "../../lib/purpose";

export default function CustomerLookup() {
  const { selected } = useConnections();
  const binding = usePurposeBinding();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get("q") || "";

  const [inputVal, setInputVal] = useState(queryParam);
  const [searchTerm, setSearchTerm] = useState(queryParam);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputVal.trim();
    if (!clean) {
      setValidationError("Please enter a full or partial Customer ID (e.g. CIF-00UKL72D or UKL72).");
      return;
    }
    setValidationError(null);
    setSearchTerm(clean);
    setSearchParams({ q: clean });
  };

  const lookupQ = useQuery({
    queryKey: ["customer-lookup", selected?.id, searchTerm, binding.purpose, binding.ticketId],
    queryFn: async () => {
      if (!selected?.id || !searchTerm) return null;

      const term = searchTerm.toUpperCase().replace(/[^A-Z0-9-]/g, "");

      const sql = /^CIF-[A-Z0-9]{8}$/.test(term)
        ? `SELECT customer_id, cust_nm, mob_no, emailid, city, state, segment, dob_dt FROM customers WHERE customer_id = '${term}' LIMIT 10`
        : `SELECT customer_id, cust_nm, mob_no, emailid, city, state, segment, dob_dt FROM customers WHERE customer_id LIKE '%${term}%' LIMIT 15`;

      const res = await apiAllowDenied("/api/query/execute", {
        body: { connection_id: selected.id, sql },
        headers: purposeHeaders(binding),
      });

      return res;
    },
    enabled: !!selected?.id && !!searchTerm,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 border-b border-[#DCE5F0] pb-4">
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
            Customer Identification & Verification
          </span>
        </div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#172B45] mt-1">Customer Lookup</h1>
        <p className="text-xs sm:text-sm text-[#64748B]">
          Find customer accounts across Saffron Bank database. Permitted fields are delivered with role-approved partial masking.
        </p>
      </div>

      <PurposeBanner results={[lookupQ.data?.ok ? lookupQ.data.body.access_context : null]} />

      {/* Search Input Card */}
      <Card title="Search Customers" subtitle="Search by full or partial Customer ID. Names and phones are masked, so they cannot be searched.">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
            <input
              type="text"
              className="input pl-9 text-sm"
              placeholder="e.g. CIF-00UKL72D or UKL72"
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
      </Card>

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
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-6 w-6 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-bold text-rose-900">Query Restricted / Access Denied</h3>
                <p className="mt-1 text-xs text-rose-800 leading-relaxed font-medium">
                  {lookupQ.data.body?.error?.message || "The query could not be executed under your role's current security policies."}
                </p>
                <div className="mt-3 text-[11px] font-mono text-rose-700">
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
              <User className="mx-auto h-8 w-8 text-[#64748B]" />
              <h3 className="mt-2 text-sm font-semibold text-[#172B45]">No Customers Found</h3>
              <p className="mt-1 text-xs text-[#64748B]">
                No customer records matched "{searchTerm}". Try another Customer ID.
              </p>
            </div>
          </Card>
        ) : (
          <Card
            title={`Search Results (${lookupQ.data.body.rows.length} records found)`}
            subtitle="Click on any customer to open their Customer 360 profile"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs min-w-[750px]">
                <thead className="border-b border-[#DCE5F0] bg-[#F4F8FD] text-[#172B45]">
                  <tr>
                    <th className="py-2.5 px-3 font-semibold">Customer ID</th>
                    <th className="py-2.5 px-3 font-semibold">Customer Name</th>
                    <th className="py-2.5 px-3 font-semibold">Mobile Number</th>
                    <th className="py-2.5 px-3 font-semibold">Email Address</th>
                    <th className="py-2.5 px-3 font-semibold">Location</th>
                    <th className="py-2.5 px-3 font-semibold">Segment</th>
                    <th className="py-2.5 px-3 text-right font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#DCE5F0] text-[#172B45]">
                  {lookupQ.data.body.rows.map((row: any[], i: number) => {
                    const [cif, name, mob, email, city, state, seg] = row;
                    return (
                      <tr key={cif || i} className="transition-colors hover:bg-[#F4F8FD]">
                        <td className="py-3 px-3 font-mono font-semibold text-[#1D5FA7]">
                          {cif}
                        </td>
                        <td className="py-3 px-3">
                          <div className="font-semibold text-[#172B45]">{name}</div>
                          <MaskBadge d={decisionOf(lookupQ.data!.body, "cust_nm")} className="mt-0.5 text-[10px]" />
                        </td>
                        <td className="py-3 px-3 font-mono text-[#172B45]">
                          <div>{mob}</div>
                          <MaskBadge d={decisionOf(lookupQ.data!.body, "mob_no")} className="mt-0.5 text-[10px]" />
                        </td>
                        <td className="py-3 px-3 text-[#172B45]">
                          <div>{email}</div>
                          <MaskBadge d={decisionOf(lookupQ.data!.body, "emailid")} className="mt-0.5 text-[10px]" />
                        </td>
                        <td className="py-3 px-3 text-[#64748B]">
                          {city && state ? `${city}, ${state}` : city || state || "—"}
                        </td>
                        <td className="py-3 px-3">
                          <Badge tone="cyan">{seg || "RETAIL"}</Badge>
                        </td>
                        <td className="py-3 px-3 text-right">
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

            <div className="mt-4 border-t border-[#DCE5F0] pt-3 text-right text-[11px] text-[#64748B]">
              Query completed in {lookupQ.data.body.duration_ms} ms · Enforced server-side masking on {lookupQ.data.body.decisions?.length || 8} columns
            </div>
          </Card>
        )
      ) : (
        /* Initial Empty Search State */
        <Card>
          <div className="py-12 text-center">
            <Search className="mx-auto h-8 w-8 text-[#64748B]" />
            <h3 className="mt-2 text-sm font-semibold text-[#172B45]">Enter a customer query</h3>
            <p className="mt-1 text-xs text-[#64748B] max-w-sm mx-auto">
              Type a Customer ID like <code>CIF-00UKL72D</code>, or part of one, to look up customer records safely.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
