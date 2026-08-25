import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Boxes,
  Check,
  ChevronDown,
  CircleDollarSign,
  Database,
  ExternalLink,
  Gauge,
  CodeXml,
  Info,
  Layers3,
  Menu,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import "./styles.css";

type Tier = "channel" | "mid_market" | "enterprise" | "strategic";

type Product = {
  id: string;
  label: string;
  family: string;
  listPrice: number;
  costRatio: number;
  history: number;
};

const products: Product[] = [
  { id: "B00003G1I1", label: "Fast Ethernet Adapter", family: "Networking", listPrice: 29.99, costRatio: 0.61, history: 22 },
  { id: "B0B5HVBK4L", label: "12-Core Desktop Processor", family: "CPU & Processor", listPrice: 299.99, costRatio: 0.54, history: 18 },
  { id: "B09J84XCLG", label: "12GB Graphics Card", family: "GPU & Graphics", listPrice: 566.48, costRatio: 0.58, history: 11 },
  { id: "B08GSS6FLK", label: "32GB Performance Memory", family: "Memory & Storage", listPrice: 94.91, costRatio: 0.66, history: 31 },
  { id: "B0C2CWRXZY", label: "Micro Business Desktop", family: "Workstation & PC", listPrice: 249.27, costRatio: 0.7, history: 9 },
];

const markets = ["UK", "IE", "DE", "FR", "NL", "ES", "BE", "CH", "PT"];

const marketFactor: Record<string, number> = {
  UK: 1.0, IE: 0.98, DE: 1.01, FR: 1.0, NL: 0.96, ES: 1.02, BE: 1.0, CH: 1.04, PT: 0.99,
};

const tierFactor: Record<Tier, number> = {
  channel: 0.88,
  mid_market: 0.94,
  enterprise: 0.86,
  strategic: 0.8,
};

const minMargin: Record<Tier, number> = {
  channel: 0.12,
  mid_market: 0.18,
  enterprise: 0.14,
  strategic: 0.1,
};

const maxDiscount: Record<Tier, number> = {
  channel: 0.28,
  mid_market: 0.18,
  enterprise: 0.25,
  strategic: 0.32,
};

const marketMetrics = [
  { market: "ES", value: 49.57 },
  { market: "DE", value: 49.39 },
  { market: "PT", value: 49.19 },
  { market: "UK", value: 49.15 },
  { market: "FR", value: 48.08 },
  { market: "BE", value: 47.98 },
  { market: "CH", value: 45.17 },
  { market: "IE", value: 33.11 },
  { market: "NL", value: 23.79 },
];

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function App() {
  const [productId, setProductId] = useState(products[1].id);
  const [market, setMarket] = useState("DE");
  const [tier, setTier] = useState<Tier>("enterprise");
  const [quantity, setQuantity] = useState(25);
  const [inventory, setInventory] = useState(6);
  const [costChange, setCostChange] = useState(2);
  const [contractCustomer, setContractCustomer] = useState(true);
  const [mobileMenu, setMobileMenu] = useState(false);

  const result = useMemo(() => {
    const product = products.find((item) => item.id === productId) ?? products[0];
    const cost = product.listPrice * product.costRatio * (1 + costChange / 100);
    const quantityDiscount = Math.max(0.78, 1 - Math.log10(Math.max(quantity, 1)) * 0.045);
    const inventoryAdjustment = inventory < 2 ? 1.055 : inventory > 10 ? 0.985 : 1;
    const contractAdjustment = contractCustomer ? 0.98 : 1;
    const modelMedian = product.listPrice * tierFactor[tier] * marketFactor[market] * quantityDiscount * inventoryAdjustment * contractAdjustment;
    const width = Math.min(0.34, 0.21 + (product.history < 10 ? 0.055 : 0) + (inventory < 2 ? 0.04 : 0));
    const lower = modelMedian * (1 - width / 2);
    const upper = modelMedian * (1 + width / 2);
    const marginFloor = cost / (1 - minMargin[tier]);
    const discountFloor = product.listPrice * (1 - maxDiscount[tier]);
    const policyFloor = Math.max(marginFloor, discountFloor);
    const recommended = Math.min(product.listPrice * 1.12, Math.max(modelMedian, policyFloor));
    const quoteValue = recommended * quantity;
    const margin = (recommended - cost) / recommended;
    const confidence = Math.exp(-2.5 * width);

    const reasons: string[] = [];
    if (quoteValue > 250_000) reasons.push("High quote value");
    if (Math.abs(costChange) > 18) reasons.push("Material cost change");
    if (inventory < 1.5) reasons.push("Low inventory");
    if (product.history < 3) reasons.push("Insufficient history");
    if (tier === "strategic") reasons.push("Strategic account review");
    if (confidence < 0.5124) reasons.push("Low model confidence");
    if (margin + 0.0001 < minMargin[tier]) reasons.push("Margin policy");

    return {
      product,
      cost,
      lower,
      upper,
      modelMedian,
      policyFloor,
      recommended,
      quoteValue,
      margin,
      confidence,
      reasons,
      approved: reasons.length === 0,
    };
  }, [productId, market, tier, quantity, inventory, costChange, contractCustomer]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Pricing Intelligence home">
          <span className="brand-mark"><Sparkles size={18} /></span>
          <span>Pricing Intelligence</span>
        </a>
        <nav className={mobileMenu ? "nav-links nav-open" : "nav-links"}>
          <a href="#overview" onClick={() => setMobileMenu(false)}>Overview</a>
          <a href="#simulator" onClick={() => setMobileMenu(false)}>Simulator</a>
          <a href="#analytics" onClick={() => setMobileMenu(false)}>Analytics</a>
          <a href="#methodology" onClick={() => setMobileMenu(false)}>Methodology</a>
        </nav>
        <div className="top-actions">
          <span className="case-badge"><Database size={14} /> Public-data case study</span>
          <a className="github-button" href="https://github.com/AkilsuryaS/enterprise-pricing-recommendation-engine" target="_blank" rel="noreferrer">
            <CodeXml size={17} /> <span>Repository</span>
          </a>
          <button className="menu-button" onClick={() => setMobileMenu(!mobileMenu)} aria-label="Toggle navigation">
            {mobileMenu ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>

      <main>
        <section className="hero" id="overview">
          <div className="hero-copy">
            <div className="eyebrow"><span className="pulse-dot" /> Decision intelligence for B2B pricing</div>
            <h1>Turn complex quotes into<br /><span>confident pricing decisions.</span></h1>
            <p>
              An interactive demonstration of quantile pricing, behavioral segmentation,
              and financial guardrails across 17,000 electronics SKUs and nine markets.
            </p>
            <div className="hero-actions">
              <a href="#simulator" className="primary-button"><SlidersHorizontal size={17} /> Try the simulator</a>
              <a href="#methodology" className="secondary-button">Explore methodology <ArrowDownRight size={17} /></a>
            </div>
          </div>
          <div className="hero-visual" aria-label="Pricing engine overview">
            <div className="visual-glow" />
            <div className="decision-card floating-card">
              <div className="decision-card-head">
                <span className="success-icon"><Check size={16} /></span>
                <div><strong>Quote approved</strong><small>All guardrails passed</small></div>
                <span className="live-pill">LIVE</span>
              </div>
              <div className="hero-price">$254.60 <small>/ unit</small></div>
              <div className="mini-range"><span style={{ left: "21%", width: "58%" }} /><i style={{ left: "52%" }} /></div>
              <div className="range-labels"><span>$228.14</span><span>recommended</span><span>$281.06</span></div>
              <div className="mini-metrics">
                <div><small>Expected margin</small><strong>35.2%</strong></div>
                <div><small>Confidence</small><strong>89.1%</strong></div>
              </div>
            </div>
            <div className="signal-card signal-one"><ShieldCheck size={18} /><span><strong>5 layers</strong>Policy protection</span></div>
            <div className="signal-card signal-two"><TrendingUp size={18} /><span><strong>4.03×</strong>Est. throughput</span></div>
          </div>
        </section>

        <section className="metric-strip" aria-label="Validated project results">
          <Metric icon={<Boxes />} value="17K" label="Catalog SKUs" detail="Real public metadata" />
          <Metric icon={<Target />} value="46.2%" label="Auto-approval" detail="Forward-time holdout" trend="up" />
          <Metric icon={<Gauge />} value="9.95%" label="P90 price error" detail="Auto-approved subset" />
          <Metric icon={<Activity />} value="92.1%" label="Interval coverage" detail="Q10–Q90 range" />
        </section>

        <section className="simulator-section" id="simulator">
          <SectionHeading eyebrow="Interactive demo" title="Quote recommendation simulator" description="Adjust commercial inputs and see how the recommendation, uncertainty range, and guardrail decision change." />

          <div className="simulator-grid">
            <div className="control-panel panel">
              <div className="panel-heading"><div><span>Quote inputs</span><small>Configure a pricing scenario</small></div><SlidersHorizontal size={19} /></div>
              <label className="field-label">Product SKU</label>
              <div className="select-wrap">
                <select value={productId} onChange={(event) => setProductId(event.target.value)}>
                  {products.map((product) => <option key={product.id} value={product.id}>{product.id} — {product.label}</option>)}
                </select>
                <ChevronDown size={17} />
              </div>
              <div className="product-context">
                <div><small>Product family</small><span>{result.product.family}</span></div>
                <div><small>List price</small><span>{money(result.product.listPrice)}</span></div>
                <div><small>Prior quotes</small><span>{result.product.history}</span></div>
              </div>

              <div className="two-columns">
                <div><label className="field-label">Market</label><div className="select-wrap"><select value={market} onChange={(event) => setMarket(event.target.value)}>{markets.map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={17} /></div></div>
                <div><label className="field-label">Customer tier</label><div className="select-wrap"><select value={tier} onChange={(event) => setTier(event.target.value as Tier)}><option value="channel">Channel</option><option value="mid_market">Mid-market</option><option value="enterprise">Enterprise</option><option value="strategic">Strategic</option></select><ChevronDown size={17} /></div></div>
              </div>

              <RangeField label="Quantity" value={quantity} min={1} max={250} step={1} suffix="units" onChange={setQuantity} />
              <RangeField label="Inventory coverage" value={inventory} min={0.5} max={18} step={0.5} suffix="weeks" onChange={setInventory} />
              <RangeField label="Cost change" value={costChange} min={-15} max={30} step={1} suffix="%" onChange={setCostChange} />

              <button className={contractCustomer ? "toggle-row toggle-on" : "toggle-row"} onClick={() => setContractCustomer(!contractCustomer)}>
                <span><strong>Contract customer</strong><small>Apply negotiated agreement context</small></span>
                <i><b /></i>
              </button>
            </div>

            <div className="recommendation-panel panel">
              <div className="panel-heading">
                <div><span>Pricing recommendation</span><small>Model estimate after policy checks</small></div>
                <span className={result.approved ? "decision-pill approved" : "decision-pill review"}>{result.approved ? <Check size={14} /> : <Info size={14} />}{result.approved ? "Auto-approve" : "Manual review"}</span>
              </div>

              <div className="recommendation-price">
                <span>Recommended unit price</span>
                <strong>{money(result.recommended)}</strong>
                <small>{money(result.quoteValue)} total quote value</small>
              </div>

              <div className="quantile-card">
                <div className="quantile-head"><span>Acceptable price range</span><strong>{money(result.lower)} – {money(result.upper)}</strong></div>
                <div className="quantile-track">
                  <span className="track-fill" />
                  <i className="median-marker" style={{ left: `${Math.min(92, Math.max(8, ((result.recommended - result.lower) / Math.max(result.upper - result.lower, 1)) * 100))}%` }} />
                </div>
                <div className="quantile-labels"><span>Q10 defensive</span><span>Q50 model median</span><span>Q90 stretch</span></div>
              </div>

              <div className="result-metrics">
                <div><span className="metric-icon green"><CircleDollarSign size={17} /></span><small>Expected margin</small><strong>{(result.margin * 100).toFixed(1)}%</strong></div>
                <div><span className="metric-icon blue"><Gauge size={17} /></span><small>Confidence</small><strong>{(result.confidence * 100).toFixed(1)}%</strong></div>
                <div><span className="metric-icon violet"><ShieldCheck size={17} /></span><small>Policy floor</small><strong>{money(result.policyFloor)}</strong></div>
              </div>

              <div className="guardrail-box">
                <div className="guardrail-title"><ShieldCheck size={18} /><span><strong>Guardrail evaluation</strong><small>Deterministic rules retain decision authority</small></span></div>
                {result.approved ? (
                  <ul className="guardrail-list">
                    <li><Check size={14} /> Margin above {Math.round(minMargin[tier] * 100)}% tier minimum</li>
                    <li><Check size={14} /> Discount within authorized range</li>
                    <li><Check size={14} /> Quote value below automatic threshold</li>
                    <li><Check size={14} /> Inventory and cost-change checks passed</li>
                  </ul>
                ) : (
                  <ul className="guardrail-list warning-list">
                    {result.reasons.map((reason) => <li key={reason}><Info size={14} /> {reason}</li>)}
                  </ul>
                )}
              </div>
              <p className="demo-note"><Info size={14} /> Interactive values use transparent demo logic aligned with the project guardrails; measured model results are shown below.</p>
            </div>
          </div>
        </section>

        <section className="analytics-section" id="analytics">
          <SectionHeading eyebrow="Forward-time evaluation" title="Performance that holds up by slice" description="The approval policy was calibrated on validation data and evaluated on a later, untouched test window." />
          <div className="analytics-grid">
            <div className="chart-panel panel">
              <div className="chart-heading"><div><strong>Auto-approval by market</strong><small>Test-period won quote lines</small></div><BarChart3 size={19} /></div>
              <div className="bar-chart">
                {marketMetrics.map((item) => (
                  <div className="bar-row" key={item.market}>
                    <span>{item.market}</span><div><i style={{ width: `${item.value * 1.7}%` }} /></div><strong>{item.value.toFixed(1)}%</strong>
                  </div>
                ))}
              </div>
              <div className="chart-legend"><span><i /> Market result</span><span><i className="benchmark-dot" /> 46.2% portfolio</span></div>
            </div>

            <div className="validation-panel panel">
              <div className="chart-heading"><div><strong>Validation summary</strong><small>Chronological test performance</small></div><Target size={19} /></div>
              <div className="score-ring"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="50" /><circle className="score-progress" cx="60" cy="60" r="50" pathLength="100" /></svg><div><strong>24.4%</strong><span>MAE improvement</span></div></div>
              <div className="validation-list">
                <div><span>Overall median APE</span><strong>4.20%</strong></div>
                <div><span>Overall p90 APE</span><strong>10.07%</strong></div>
                <div><span>Q10–Q90 coverage</span><strong>92.06%</strong></div>
                <div><span>Observed test wins</span><strong>21,109</strong></div>
              </div>
            </div>

            <div className="impact-panel panel">
              <div className="impact-icon"><TrendingUp size={22} /></div>
              <span>Estimated operational impact</span>
              <strong>4.03×</strong>
              <p>Analyst throughput under documented handling-time assumptions.</p>
              <div className="impact-comparison"><div><span>Manual baseline</span><strong>10.0 min</strong></div><ArrowUpRight size={18} /><div><span>Blended handling</span><strong>2.48 min</strong></div></div>
            </div>
          </div>
        </section>

        <section className="method-section" id="methodology">
          <SectionHeading eyebrow="Transparent methodology" title="Built for auditability, not black-box automation" description="Every layer separates statistical estimation from deterministic commercial policy." />
          <div className="method-grid">
            <MethodCard number="01" icon={<Database />} title="Public data foundation" text="Real product metadata and 1,067,371 transaction lines establish catalog and market behavior." />
            <MethodCard number="02" icon={<Layers3 />} title="Behavioral segmentation" text="Training-period K-Means features group products by price, demand, quantity, and historical outcomes." />
            <MethodCard number="03" icon={<Activity />} title="Quantile prediction" text="Three XGBoost models estimate Q10, Q50, and Q90 accepted-price outcomes and uncertainty." />
            <MethodCard number="04" icon={<ShieldCheck />} title="Policy decisioning" text="Margin, discount, inventory, cost, history, and strategic-account rules control automation." />
          </div>
          <div className="disclosure panel">
            <div className="disclosure-icon"><Info size={20} /></div>
            <div><strong>Data transparency</strong><p>Product and transaction-derived signals come from public sources. Confidential commercial fields—including costs, contracts, inventory, customer tiers, quote outcomes, and analyst time—are explicitly simulated. Results demonstrate the system design and do not represent measured company impact.</p></div>
            <a href="https://github.com/AkilsuryaS/enterprise-pricing-recommendation-engine/blob/main/docs/DATA_CARD.md" target="_blank" rel="noreferrer">Read the data card <ExternalLink size={15} /></a>
          </div>
        </section>
      </main>

      <footer>
        <div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>Pricing Intelligence</span></div>
        <p>Enterprise pricing recommendation engine · Public-data case study</p>
        <a href="https://github.com/AkilsuryaS/enterprise-pricing-recommendation-engine" target="_blank" rel="noreferrer"><CodeXml size={16} /> View source</a>
      </footer>
    </div>
  );
}

function Metric({ icon, value, label, detail, trend }: { icon: ReactNode; value: string; label: string; detail: string; trend?: "up" }) {
  return <div className="strip-metric"><span className="strip-icon">{icon}</span><div><strong>{value}</strong><span>{label}</span><small>{detail}</small></div>{trend && <ArrowUpRight className="trend-icon" size={18} />}</div>;
}

function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="section-heading"><span>{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>;
}

function RangeField({ label, value, min, max, step, suffix, onChange }: { label: string; value: number; min: number; max: number; step: number; suffix: string; onChange: (value: number) => void }) {
  const progress = ((value - min) / (max - min)) * 100;
  return <div className="range-field"><div className="range-field-head"><label>{label}</label><span>{value} {suffix}</span></div><input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} style={{ "--progress": `${progress}%` } as CSSProperties} /><div className="range-minmax"><span>{min}</span><span>{max}</span></div></div>;
}

function MethodCard({ number, icon, title, text }: { number: string; icon: ReactNode; title: string; text: string }) {
  return <article className="method-card"><span className="method-number">{number}</span><span className="method-icon">{icon}</span><h3>{title}</h3><p>{text}</p></article>;
}

createRoot(document.getElementById("root")!).render(<App />);
