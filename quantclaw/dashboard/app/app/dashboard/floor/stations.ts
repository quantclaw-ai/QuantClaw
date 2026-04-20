export interface StationConfig {
  name: string;
  displayName: string;
  displayNameZh: string;
  displayNameJa: string;
  zone: string;
  zoneZh: string;
  zoneJa: string;
  x: number;
  y: number;
  width: number;
  height: number;
  theme: {
    props: string[];
    busyAnimation: string;
    color: string;
    icon: string; // emoji/symbol for the station
  };
}

export const STATIONS: StationConfig[] = [
  // Command Center
  { name: "scheduler", displayName: "Scheduler", displayNameZh: "调度器", displayNameJa: "スケジューラー",
    zone: "Command Center", zoneZh: "指挥中心", zoneJa: "コマンドセンター",
    x: 60, y: 50, width: 130, height: 110,
    theme: { props: ["reception_desk", "workflow_board", "megaphone"], busyAnimation: "cards_shuffle", color: "#f59e0b", icon: "S" }},
  { name: "sentinel", displayName: "Sentinel", displayNameZh: "哨兵", displayNameJa: "センチネル",
    zone: "Command Center", zoneZh: "指挥中心", zoneJa: "コマンドセンター",
    x: 60, y: 200, width: 130, height: 110,
    theme: { props: ["watchtower", "radar", "binoculars"], busyAnimation: "radar_sweep", color: "#f43f5e", icon: "W" }},

  // Data Room
  { name: "ingestor", displayName: "Ingestor", displayNameZh: "采集器", displayNameJa: "インジェスター",
    zone: "Data Room", zoneZh: "数据室", zoneJa: "データルーム",
    x: 60, y: 390, width: 130, height: 110,
    theme: { props: ["data_pipes", "satellite_dish", "monitors"], busyAnimation: "pipes_flow", color: "#3b82f6", icon: "D" }},

  // Quant Lab
  { name: "validator", displayName: "Validator", displayNameZh: "校验器", displayNameJa: "バリデーター",
    zone: "Quant Lab", zoneZh: "量化实验室", zoneJa: "クオンツラボ",
    x: 280, y: 50, width: 130, height: 110,
    theme: { props: ["time_machine", "rewind_dials", "equity_curve", "verification_seal"], busyAnimation: "dials_spin", color: "#14b8a6", icon: "V" }},
  { name: "miner", displayName: "Miner", displayNameZh: "矿工", displayNameJa: "マイナー",
    zone: "Quant Lab", zoneZh: "量化实验室", zoneJa: "クオンツラボ",
    x: 280, y: 200, width: 130, height: 110,
    theme: { props: ["pickaxe", "ore_cart", "crystals"], busyAnimation: "pickaxe_swing", color: "#ef4444", icon: "M" }},
  { name: "trainer", displayName: "Trainer", displayNameZh: "训练器", displayNameJa: "トレーナー",
    zone: "Quant Lab", zoneZh: "量化实验室", zoneJa: "クオンツラボ",
    x: 280, y: 350, width: 130, height: 110,
    theme: { props: ["neural_network", "brain_jar", "training_bars"], busyAnimation: "nodes_pulse", color: "#ec4899", icon: "T" }},
  { name: "researcher", displayName: "Researcher", displayNameZh: "研究员", displayNameJa: "リサーチャー",
    zone: "Quant Lab", zoneZh: "量化实验室", zoneJa: "クオンツラボ",
    x: 280, y: 500, width: 130, height: 110,
    theme: { props: ["library_desk", "magnifying_glass", "lightbulb"], busyAnimation: "pages_flip", color: "#06b6d4", icon: "R" }},

  // Trading Desk
  { name: "executor", displayName: "Executor", displayNameZh: "执行器", displayNameJa: "エグゼキューター",
    zone: "Trading Desk", zoneZh: "交易台", zoneJa: "トレーディングデスク",
    x: 500, y: 50, width: 130, height: 110,
    theme: { props: ["bloomberg_terminal", "order_blotter", "buy_sell_lights"], busyAnimation: "lights_flash", color: "#22c55e", icon: "E" }},
  { name: "risk_monitor", displayName: "Risk Monitor", displayNameZh: "风控监控", displayNameJa: "リスクモニター",
    zone: "Trading Desk", zoneZh: "交易台", zoneJa: "トレーディングデスク",
    x: 500, y: 200, width: 130, height: 110,
    theme: { props: ["gauges", "warning_lights", "shield"], busyAnimation: "gauges_swing", color: "#a855f7", icon: "K" }},

  // Back Office
  { name: "reporter", displayName: "Reporter", displayNameZh: "报告员", displayNameJa: "レポーター",
    zone: "Back Office", zoneZh: "后台办公", zoneJa: "バックオフィス",
    x: 720, y: 50, width: 130, height: 110,
    theme: { props: ["printing_press", "papers", "wall_charts"], busyAnimation: "printer_output", color: "#f97316", icon: "P" }},
  { name: "compliance", displayName: "Compliance", displayNameZh: "合规", displayNameJa: "コンプライアンス",
    zone: "Back Office", zoneZh: "后台办公", zoneJa: "バックオフィス",
    x: 720, y: 350, width: 130, height: 110,
    theme: { props: ["filing_cabinet", "stamp", "scales"], busyAnimation: "stamp_pound", color: "#6366f1", icon: "C" }},

  // Debug Bay
  { name: "debugger", displayName: "Debugger", displayNameZh: "调试器", displayNameJa: "デバッガー",
    zone: "Debug Bay", zoneZh: "调试区", zoneJa: "デバッグベイ",
    x: 500, y: 390, width: 130, height: 110,
    theme: { props: ["workbench", "bug_jar", "circuit_boards"], busyAnimation: "magnify_scan", color: "#eab308", icon: "X" }},
];

export function getStationByName(name: string): StationConfig | undefined {
  return STATIONS.find((s) => s.name === name);
}

export function getStationDisplayName(station: StationConfig, lang: string): string {
  if (lang === "zh") return station.displayNameZh;
  if (lang === "ja") return station.displayNameJa;
  return station.displayName;
}

export function getZoneDisplayName(station: StationConfig, lang: string): string {
  if (lang === "zh") return station.zoneZh;
  if (lang === "ja") return station.zoneJa;
  return station.zone;
}
