export const metadata = {
  title: "About — Solar WiFi Placement Optimizer",
};

export default function AboutPage() {
  return (
    <div className="about-content">
      <h1>How it works</h1>
      <p>
        Given the rated range of an access point on each frequency band, the tool computes the
        minimum number of solar-powered WiFi access points needed to cover a site — a park,
        cemetery, or campus — and where to put them. Everything below runs against free, keyless
        public data sources; nothing here needs an API key.
      </p>

      <div className="pipeline-steps">
        <div className="pipeline-step">
          <span className="step-num">1</span>
          <div>
            <strong>OpenStreetMap topology.</strong> Fetches the site boundary, tree canopy,
            building footprints, and walkable paths from OpenStreetMap (via the Overpass API).
          </div>
        </div>
        <div className="pipeline-step">
          <span className="step-num">2</span>
          <div>
            <strong>Elevation grid.</strong> Samples a bare-earth elevation grid over the site
            from a free point-query API, then paints tree canopy and building footprints onto it
            to build the digital surface model used for line-of-sight analysis.
          </div>
        </div>
        <div className="pipeline-step">
          <span className="step-num">3</span>
          <div>
            <strong>Solar irradiance.</strong> Pulls multi-year monthly solar irradiance (GHI) and
            temperature data from NASA POWER to determine, per month, how much energy a panel at
            this latitude can realistically harvest.
          </div>
        </div>
        <div className="pipeline-step">
          <span className="step-num">4</span>
          <div>
            <strong>RF propagation.</strong> Models radio line-of-sight between every candidate AP
            location and every point that needs coverage, applying the ITU-R P.833 vegetation
            attenuation model to account for signal loss through tree canopy.
          </div>
        </div>
        <div className="pipeline-step">
          <span className="step-num">5</span>
          <div>
            <strong>Solar viability per candidate.</strong> For each candidate site, checks whether
            a 100 W solar panel, 10 W continuous load, and 50 Wh battery can sustain the node
            through the worst above-freezing month with sufficient sun — flagging locations as
            solar-viable or marginal (may need a better-sited panel).
          </div>
        </div>
        <div className="pipeline-step">
          <span className="step-num">6</span>
          <div>
            <strong>ILP set-cover solve.</strong> Formulates AP placement as an Integer Linear
            Program — minimize the number of access points such that every point requiring
            coverage is within range of at least one AP with clear line-of-sight — and solves it
            with HiGHS.
          </div>
        </div>
      </div>

      <h2>Hardware assumptions (per AP node)</h2>
      <table>
        <tbody>
          <tr>
            <td>Solar panel</td>
            <td>100 W rated</td>
          </tr>
          <tr>
            <td>Load</td>
            <td>10 W continuous</td>
          </tr>
          <tr>
            <td>Battery</td>
            <td>50 Wh</td>
          </tr>
          <tr>
            <td>Derating factor</td>
            <td>0.80 (temperature, wiring, soiling)</td>
          </tr>
          <tr>
            <td>Design basis</td>
            <td>Worst above-freezing month with sufficient sun (e.g. ~October for Brooklyn)</td>
          </tr>
          <tr>
            <td>Thermal cutoff</td>
            <td>Below ~34°F average monthly temperature</td>
          </tr>
        </tbody>
      </table>

      <h2>Notes</h2>
      <ul>
        <li>
          All external data is cached after the first fetch, so repeated runs for the same site
          are fast and fully offline.
        </li>
        <li>
          Some months — November and December in Brooklyn, for example — have insufficient sun for
          24/7 operation even with a fully exposed panel; these are flagged as shoulder months in
          the results.
        </li>
        <li>
          This started as a CLI tool hardcoded to Green-Wood Cemetery in Brooklyn, NY, and has been
          generalized to run against any coordinates worldwide where OpenStreetMap, the elevation
          API, and NASA POWER have coverage.
        </li>
        <li>
          Green AP pins on the map are solar-viable; yellow pins are marginal and may need a
          better-sited panel.
        </li>
      </ul>
    </div>
  );
}
