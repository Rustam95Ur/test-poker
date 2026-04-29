import { useEffect, useMemo, useState } from "react";

const API_BASE = "/api/v1";

function fmtPercent(value) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function App() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [spot, setSpot] = useState("ALL");
  const [formation, setFormation] = useState("ALL");
  const [position, setPosition] = useState("ALL");
  const [role, setRole] = useState("ALL");
  const [line, setLine] = useState("ALL");
  const [street, setStreet] = useState("ALL");
  const [selectedStatId, setSelectedStatId] = useState("");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE}/stats`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setItems(data.items || []);
      } catch (e) {
        setError(`Failed to load stats: ${e.message}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const spots = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.spot));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((x) => {
      const stat = x.stat;
      if (spot !== "ALL" && stat.spot !== spot) return false;
      if (formation !== "ALL" && stat.formation !== formation) return false;
      if (position !== "ALL" && stat.position !== position) return false;
      if (role !== "ALL" && stat.role !== role) return false;
      if (line !== "ALL" && stat.line !== line) return false;
      if (street !== "ALL" && stat.street !== street) return false;
      return true;
    });
  }, [items, spot, formation, position, role, line, street]);

  const formations = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.formation));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const positions = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.position));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const roles = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.role));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const lines = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.line));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const streets = useMemo(() => {
    const uniq = new Set(items.map((x) => x.stat.street));
    return ["ALL", ...Array.from(uniq)];
  }, [items]);

  const selectedRow = useMemo(
    () => filtered.find((x) => x.stat.id === selectedStatId) || null,
    [filtered, selectedStatId]
  );

  return (
    <div className="page">
      <h1>Mini Poker Stats Explorer</h1>
      <p className="caption">
        Population vs GTO from local files, no DB required.
      </p>

      <div className="toolbar">
        <label>
          Spot:
          <select value={spot} onChange={(e) => setSpot(e.target.value)}>
            {spots.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Formation:
          <select value={formation} onChange={(e) => setFormation(e.target.value)}>
            {formations.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Position:
          <select value={position} onChange={(e) => setPosition(e.target.value)}>
            {positions.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Role:
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Line:
          <select value={line} onChange={(e) => setLine(e.target.value)}>
            {lines.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Street:
          <select value={street} onChange={(e) => setStreet(e.target.value)}>
            {streets.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        <table>
          <thead>
            <tr>
              <th>Stat</th>
              <th>Spot</th>
              <th>Population</th>
              <th>GTO</th>
              <th>Delta</th>
              <th>Population sample</th>
              <th>GTO sample</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr
                key={row.stat.id}
                className={selectedStatId === row.stat.id ? "selected-row" : ""}
                onClick={() => setSelectedStatId(row.stat.id)}
              >
                <td>{row.stat.label}</td>
                <td>{row.stat.spot}</td>
                <td>{fmtPercent(row.population.value)}</td>
                <td>{fmtPercent(row.gto.value)}</td>
                <td>{fmtPercent(row.delta)}</td>
                <td>
                  {row.population.numerator ?? "-"} /{" "}
                  {row.population.denominator ?? "-"}
                </td>
                <td>
                  {row.gto.numerator ?? "-"} / {row.gto.denominator ?? "-"}
                </td>
                <td>
                  pop: {row.population.sampleStatus}, gto:{" "}
                  {row.gto.sampleStatus}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && !error && selectedRow && (
        <div className="details">
          <h2>Matched hands preview: {selectedRow.stat.label}</h2>
          <div className="details-grid">
            <div>
              <h3>Population</h3>
              {selectedRow.population.matchedHands.length === 0 ? (
                <p className="caption">No matched hands in numerator.</p>
              ) : (
                <pre>
                  {JSON.stringify(selectedRow.population.matchedHands, null, 2)}
                </pre>
              )}
            </div>
            <div>
              <h3>GTO</h3>
              {selectedRow.gto.matchedHands.length === 0 ? (
                <p className="caption">No matched hands in numerator.</p>
              ) : (
                <pre>{JSON.stringify(selectedRow.gto.matchedHands, null, 2)}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
