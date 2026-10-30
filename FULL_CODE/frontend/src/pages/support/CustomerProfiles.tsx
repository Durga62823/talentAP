import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CreditCard,
  Lock,
  Mail,
  MapPin,
  Phone,
  Search,
  User,
  Wallet,
} from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { apiAllowDenied } from "../../lib/api";
import { useConnections } from "../../lib/connections";

export default function CustomerProfiles() {
  const { selected } = useConnections();
  const [searchParams, setSearchParams] = useSearchParams();
  const cif = searchParams.get("id") || "CIF-00UKL72D";
  const [switchVal, setSwitchVal] = useState(cif);

  // 1. Customer Personal & Contact Record
  const customerQ = useQuery({
    queryKey: ["customer-profile-main", selected?.id, cif],
    queryFn: async () => {
      if (!selected?.id || !cif) return null;
      const cleanCif = cif.replace(/['"\\]/g, "");
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: `SELECT customer_id, cust_nm, gender, dob_dt, mob_no, emailid, addr_line1, city, state, pincode, segment, risk_cat, preferred_lang, customer_since FROM customers WHERE customer_id = '${cleanCif}' LIMIT 1`,
        },
      });
      return res;
    },
    enabled: !!selected?.id && !!cif,
  });

  // 2. Linked Accounts
  const accountsQ = useQuery({
    queryKey: ["customer-profile-accounts", selected?.id, cif],
    queryFn: async () => {
      if (!selected?.id || !cif) return null;
      const cleanCif = cif.replace(/['"\\]/g, "");
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: `SELECT account_no, branch_code, acct_type, curr_bal, open_dt, acct_status FROM accounts WHERE customer_id = '${cleanCif}'`,
        },
      });
      return res;
    },
    enabled: !!selected?.id && !!cif,
  });

  // 3. Linked Cards
  const cardsQ = useQuery({
    queryKey: ["customer-profile-cards", selected?.id, cif],
    queryFn: async () => {
      if (!selected?.id || !cif) return null;
      const cleanCif = cif.replace(/['"\\]/g, "");
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: `SELECT CARD_REF, CARD_NO, CARD_NETWORK, CARD_TYPE, NAME_ON_CARD, CREDIT_LIMIT, CARD_STATUS, ISSUED_ON FROM cards WHERE CUSTOMER_ID = '${cleanCif}'`,
        },
      });
      return res;
    },
    enabled: !!selected?.id && !!cif,
  });

  // 4. Customer Support Tickets History
  const ticketsQ = useQuery({
    queryKey: ["customer-profile-tickets", selected?.id, cif],
    queryFn: async () => {
      if (!selected?.id || !cif) return null;
      const cleanCif = cif.replace(/['"\\]/g, "");
      const res = await apiAllowDenied("/api/query/execute", {
        body: {
          connection_id: selected.id,
          sql: `SELECT ticket_id, channel, category, priority, status, created_ts, ticket_text FROM support_tickets WHERE customer_id = '${cleanCif}' ORDER BY ticket_id DESC LIMIT 10`,
        },
      });
      return res;
    },
    enabled: !!selected?.id && !!cif,
  });

  const handleSwitch = (e: React.FormEvent) => {
    e.preventDefault();
    if (switchVal.trim()) {
      setSearchParams({ id: switchVal.trim().toUpperCase() });
    }
  };

  const custData = customerQ.data?.ok && customerQ.data?.body?.rows?.[0] ? customerQ.data.body.rows[0] : null;

  return (
    <div className="space-y-6">
      {/* Header & CIF Switcher */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE5F0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#DCE5F0] bg-[#EAF2FB] px-2 py-0.5 text-xs font-semibold uppercase text-[#123B67]">
              Customer 360° Profile
            </span>
            <span className="text-xs text-[#64748B]">· Support Access Control</span>
          </div>
          <h1 className="mt-1 text-xl sm:text-2xl font-bold tracking-tight text-[#172B45]">
            {custData ? custData[1] : cif}
          </h1>
          <p className="text-xs font-semibold text-[#1D5FA7] font-mono">Customer ID: {cif}</p>
        </div>

        {/* Quick CIF Switcher */}
        <form onSubmit={handleSwitch} className="flex items-center gap-2 w-full sm:w-auto">
          <input
            type="text"
            className="input h-9 text-xs flex-1 sm:w-44 font-mono uppercase"
            placeholder="CIF-..."
            value={switchVal}
            onChange={(e) => setSwitchVal(e.target.value)}
          />
          <Button size="sm" variant="secondary" type="submit" icon={<Search className="h-3.5 w-3.5" />}>
            Load
          </Button>
        </form>
      </div>

      {customerQ.isLoading ? (
        <Card>
          <div className="py-12">
            <Spinner label="Loading customer profile..." />
          </div>
        </Card>
      ) : !custData ? (
        <Card>
          <div className="py-12 text-center">
            <AlertCircle className="mx-auto h-8 w-8 text-rose-600" />
            <h3 className="mt-2 text-sm font-semibold text-[#172B45]">Customer Record Not Found</h3>
            <p className="mt-1 text-xs text-[#64748B]">
              No record found for Customer ID "{cif}" in the active database.
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Section 1: Customer Contact & Demographics (2 cols) */}
          <div className="space-y-6 lg:col-span-2">
            <Card
              title="Personal & Contact Details"
              subtitle="Identity verification information with dynamic server-side masking"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center justify-between text-xs text-[#64748B]">
                    <span className="flex items-center gap-1.5 font-semibold text-[#172B45]">
                      <User className="h-3.5 w-3.5 text-[#1D5FA7]" /> Full Name
                    </span>
                    <Badge tone="amber">Partially Masked</Badge>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#172B45]">{custData[1]}</div>
                </div>

                <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center justify-between text-xs text-[#64748B]">
                    <span className="flex items-center gap-1.5 font-semibold text-[#172B45]">
                      <Phone className="h-3.5 w-3.5 text-[#1D5FA7]" /> Mobile Number
                    </span>
                    <Badge tone="amber">Partially Masked</Badge>
                  </div>
                  <div className="mt-1 font-mono text-sm font-semibold text-[#172B45]">{custData[4]}</div>
                </div>

                <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center justify-between text-xs text-[#64748B]">
                    <span className="flex items-center gap-1.5 font-semibold text-[#172B45]">
                      <Mail className="h-3.5 w-3.5 text-[#1D5FA7]" /> Email Address
                    </span>
                    <Badge tone="amber">Partially Masked</Badge>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#172B45]">{custData[5]}</div>
                </div>

                <div className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center justify-between text-xs text-[#64748B]">
                    <span className="flex items-center gap-1.5 font-semibold text-[#172B45]">
                      <Calendar className="h-3.5 w-3.5 text-[#1D5FA7]" /> Date of Birth
                    </span>
                    <Badge tone="cyan">Generalized</Badge>
                  </div>
                  <div className="mt-1 font-mono text-sm font-semibold text-[#172B45]">{custData[3] || "—"}</div>
                </div>

                <div className="sm:col-span-2 rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3.5">
                  <div className="flex items-center justify-between text-xs text-[#64748B]">
                    <span className="flex items-center gap-1.5 font-semibold text-[#172B45]">
                      <MapPin className="h-3.5 w-3.5 text-[#1D5FA7]" /> Postal Address
                    </span>
                    <Badge tone="amber">Partially Masked</Badge>
                  </div>
                  <div className="mt-1 text-sm font-medium text-[#172B45]">{custData[6]}</div>
                  <div className="mt-0.5 text-xs text-[#64748B]">
                    {custData[7]}, {custData[8]} - {custData[9]}
                  </div>
                </div>
              </div>
            </Card>

            {/* Linked Bank Accounts */}
            <Card
              title="Linked Accounts"
              subtitle="Bank accounts held with Saffron Bank Ltd"
            >
              {accountsQ.isLoading ? (
                <div className="py-6"><Spinner label="Loading accounts..." /></div>
              ) : accountsQ.data?.ok && accountsQ.data?.body?.rows?.length ? (
                <div className="space-y-3">
                  {accountsQ.data.body.rows.map((acc: any[]) => (
                    <div
                      key={acc[0]}
                      className="flex flex-col gap-3 rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7]">
                          <Wallet className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-bold text-[#172B45]">{acc[0]}</span>
                            <Badge tone="green">Visible</Badge>
                          </div>
                          <div className="text-xs text-[#64748B]">
                            Type: {acc[2]} · Branch: {acc[1]} · Opened: {acc[4]}
                          </div>
                        </div>
                      </div>

                      <div className="text-left sm:text-right">
                        <div className="text-xs text-[#64748B]">Running Balance</div>
                        <div className="mt-0.5 flex items-center justify-start sm:justify-end gap-1.5">
                          <span className="font-mono text-xs font-semibold text-rose-700">
                            {acc[3] !== undefined && acc[3] !== null ? String(acc[3]) : "[REDACTED]"}
                          </span>
                          <Badge tone="red">Redacted by Policy</Badge>
                        </div>
                        <div className="text-[10px] text-[#64748B]">
                          Policy #80: Support restricted from running balances
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-4 text-xs text-[#64748B]">No bank accounts linked to this customer.</div>
              )}
            </Card>

            {/* Linked Cards */}
            <Card
              title="Active Payment Cards"
              subtitle="Credit and debit cards issued under this customer"
            >
              {cardsQ.isLoading ? (
                <div className="py-6"><Spinner label="Loading cards..." /></div>
              ) : cardsQ.data?.ok && cardsQ.data?.body?.rows?.length ? (
                <div className="space-y-3">
                  {cardsQ.data.body.rows.map((card: any[]) => (
                    <div
                      key={card[0]}
                      className="flex flex-col gap-3 rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#EAF2FB] text-[#1D5FA7]">
                          <CreditCard className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-bold text-[#123B67]">{card[1]}</span>
                            <Badge tone="amber">Partially Masked</Badge>
                          </div>
                          <div className="text-xs text-[#64748B]">
                            {card[2]} {card[3]} · Name: {card[4]} · Issued: {card[7] || "—"}
                          </div>
                        </div>
                      </div>

                      <div className="text-left sm:text-right">
                        <div className="text-xs text-[#64748B]">Credit Limit (Permitted Quote)</div>
                        <div className="mt-0.5 flex items-center justify-start sm:justify-end gap-1.5">
                          <span className="font-mono text-sm font-semibold text-emerald-700">
                            {card[5] ? `₹${Number(card[5]).toLocaleString()}` : "—"}
                          </span>
                          <Badge tone="green">Allowed</Badge>
                        </div>
                        <div className="text-[10px] text-[#64748B]">
                          Policy #79: Support permitted to quote credit limit
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-4 text-xs text-[#64748B]">No active payment cards linked to this customer.</div>
              )}
            </Card>
          </div>

          {/* Section 2: Account Context & Support History (1 col) */}
          <div className="space-y-6">
            {/* Customer Account Summary Card */}
            <Card title="Account Context">
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-[#DCE5F0] pb-2">
                  <span className="text-[#64748B]">Customer ID</span>
                  <span className="font-mono font-semibold text-[#1D5FA7]">{custData[0]}</span>
                </div>
                <div className="flex items-center justify-between border-b border-[#DCE5F0] pb-2">
                  <span className="text-[#64748B]">Customer Segment</span>
                  <Badge tone="cyan">{custData[10] || "RETAIL"}</Badge>
                </div>
                <div className="flex items-center justify-between border-b border-[#DCE5F0] pb-2">
                  <span className="text-[#64748B]">Risk Category</span>
                  <Badge tone={custData[11] === "HIGH" ? "red" : "neutral"}>{custData[11] || "LOW"}</Badge>
                </div>
                <div className="flex items-center justify-between border-b border-[#DCE5F0] pb-2">
                  <span className="text-[#64748B]">Preferred Language</span>
                  <span className="font-medium text-[#172B45]">{custData[12] || "English"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[#64748B]">Customer Since</span>
                  <span className="font-mono text-[#172B45]">{custData[13] || "2021-04-12"}</span>
                </div>
              </div>
            </Card>

            {/* Support Ticket History */}
            <Card
              title="Support Case History"
              subtitle="Previous customer inquiries"
              actions={
                <Link to="/support/tickets" className="text-xs font-semibold text-[#1D5FA7] hover:underline">
                  All tickets →
                </Link>
              }
            >
              {ticketsQ.isLoading ? (
                <div className="py-6"><Spinner label="Loading cases..." /></div>
              ) : ticketsQ.data?.ok && ticketsQ.data?.body?.rows?.length ? (
                <div className="space-y-2.5">
                  {ticketsQ.data.body.rows.map((t: any[]) => (
                    <div
                      key={t[0]}
                      className="rounded-lg border border-[#DCE5F0] bg-[#F4F8FD] p-3 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-semibold text-[#123B67]">{t[0]}</span>
                        <Badge
                          tone={
                            t[4] === "OPEN"
                              ? "amber"
                              : t[4] === "RESOLVED" || t[4] === "CLOSED"
                                ? "green"
                                : "cyan"
                          }
                        >
                          {t[4]}
                        </Badge>
                      </div>
                      <div className="mt-1 font-semibold text-[#172B45]">{t[2]}</div>
                      <p className="mt-1 text-[11px] text-[#64748B] line-clamp-2">{t[6]}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-4 text-xs text-[#64748B]">No support tickets logged for this customer.</div>
              )}
            </Card>

            {/* Unauthorized Resources Note */}
            <div className="rounded-xl border border-[#DCE5F0] bg-[#F4F8FD] p-4 text-xs text-[#64748B] shadow-sm">
              <div className="flex items-center gap-2 font-semibold text-[#172B45]">
                <Lock className="h-4 w-4 text-[#1D5FA7]" /> Restricted Information
              </div>
              <p className="mt-1.5 leading-relaxed text-[#64748B]">
                Loan applications and credit underwriting dossiers are strictly inaccessible to the Customer Support role. Attempts to query these tables are blocked and logged in the security audit trail.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
