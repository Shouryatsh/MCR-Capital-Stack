import { fmtBillions, fmtDate, fmtMm, fmtPct, fmtPp, fmtSignedPct, fmtSignedUsd, fmtUsd, toCsv } from "../lib/format";

describe("financial formatting", () => {
  it("shows exact whole dollars with thousands separators and no rounding", () => {
    expect(fmtUsd(2_613_623_651_000)).toBe("$2,613,623,651,000");
    expect(fmtUsd(2_613_623_651_001)).toBe("$2,613,623,651,001");
    expect(fmtUsd(3_010_690_643_000)).toBe("$3,010,690,643,000");
    expect(fmtUsd(null)).toBe("—");
  });

  it("keeps every digit of the largest values we handle (below 2^53)", () => {
    const n = 9_007_199_254_740_991;
    expect(fmtUsd(n)).toBe("$9,007,199,254,740,991");
  });

  it("signs changes explicitly", () => {
    expect(fmtSignedUsd(171_272_556_000)).toBe("+$171,272,556,000");
    expect(fmtSignedUsd(-17_113_858_000)).toBe("−$17,113,858,000");
    expect(fmtSignedPct(7.0126)).toBe("+7.01%");
    expect(fmtSignedPct(-10.8386)).toBe("−10.84%");
    expect(fmtSignedPct(0)).toBe("0.00%");
    expect(fmtSignedPct(null)).toBe("—");
  });

  it("formats ratios and percentage-point moves like the Streamlit app", () => {
    expect(fmtPct(0.014882, 2)).toBe("1.49%");
    expect(fmtPct(0.014882, 4)).toBe("1.4882%");
    expect(fmtPp(0.0002)).toBe("+0.02 pp");
    expect(fmtPp(-0.0001)).toBe("−0.01 pp");
    expect(fmtMm(4_434_746)).toBe("4,434,746");
    expect(fmtMm(null)).toBe("—");
  });

  it("parses reporting dates as UTC so the day never shifts with the viewer's time zone", () => {
    expect(fmtDate("2023-09-30")).toBe("September 30, 2023");
    expect(fmtDate("2022-09-30")).toBe("September 30, 2022");
  });

  it("uses billions only as chart shorthand", () => {
    expect(fmtBillions(3_010_690_643_000)).toBe("$3,010.7B");
  });

  it("writes CSV with quoting and exact integers", () => {
    expect(toCsv([{ a: "x,y", b: 2_613_623_651_000, c: 'say "hi"', d: null }])).toBe('a,b,c,d\r\n"x,y",2613623651000,"say ""hi""",');
    expect(toCsv([])).toBe("");
  });
});
