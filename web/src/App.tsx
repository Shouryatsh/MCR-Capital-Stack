import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { CalculationsPage } from "./pages/CalculationsPage";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SourceValuesPage } from "./pages/SourceValuesPage";
import { SummaryPage } from "./pages/SummaryPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="benchmark" element={<BenchmarkPage />} />
        <Route path="calculations" element={<CalculationsPage />} />
        <Route path="summary" element={<SummaryPage />} />
        <Route path="source-values" element={<SourceValuesPage />} />
        <Route path="gnma" element={<Navigate to="/source-values?entity=gnma" replace />} />
        <Route path="sources" element={<DataSourcesPage />} />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
