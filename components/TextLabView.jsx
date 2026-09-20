"use client";

// 文字实验室页。这一节多了一件事：把历史记录显示出来。
// 历史放在弹窗里（而不是再加一张卡），点结果卡右上角的按钮才打开——
// 也是打开的那一刻才去请求 /api/history，没必要每次进页面都拉一遍。
import { useState } from "react";
import Nav from "./Nav.jsx";
import PageHeading from "./PageHeading.jsx";
import AnimatedCardGrid from "./AnimatedCardGrid.jsx";
import InputCard from "./InputCard.jsx";
import ResultCard from "./ResultCard.jsx";
import HistoryModal from "./HistoryModal.jsx";
import { textLab } from "../data/site.js";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "";

export default function TextLabView() {
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  async function openHistory() {
    setHistoryOpen(true);
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const res = await fetch(`${API}/api/history`, {credentials: "include"});
      if (!res.ok) throw new Error(`历史记录加载失败：${res.status}`);
      const items = await res.json();
      if (!Array.isArray(items)) throw new Error("历史记录返回格式不正确");
      setHistory(items);
    } catch (error) {
      setHistoryError(error.message || "历史记录加载失败，请稍后重试");
    } finally {
      setHistoryLoading(false);
    }
  }

  return (
    <AnimatedCardGrid className="dashboard-grid">
      <article className="hero-stage panel-full">
        <Nav />
        <PageHeading title={textLab.heroTitle} subtitle={textLab.heroSubtitle} />
      </article>

      <InputCard onResult={setResult} />
      <ResultCard result={result} onOpenHistory={openHistory} />

      <HistoryModal
        open={historyOpen}
        items={history}
        loading={historyLoading}
        error={historyError}
        onClose={() => setHistoryOpen(false)}
      />
    </AnimatedCardGrid>
  );
}
