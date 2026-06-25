/** Dev-only demo accuracy data — never used in production builds. */
export const DEV_ACCURACY_DEMO = {
  overall_accuracy: 0.732,
  total_predictions: 863,
  correct_predictions: 632,
  wrong_predictions: 231,
  pending_predictions: 0,
  accuracy_by_market: [
    { market: "1X2", total: 863, correct: 632, wrong: 231, pending: 0, accuracy: 0.732 },
    { market: "Over/Under 2.5", total: 820, correct: 590, wrong: 230, pending: 0, accuracy: 0.719 },
    { market: "BTTS", total: 800, correct: 560, wrong: 240, pending: 0, accuracy: 0.7 },
  ],
  recent_results: [
    { fixture_id: 1, match_name: "Demo Home vs Demo Away", market: "1X2", prediction: "home", actual_result: "home_win", status: "correct", confidence: 74, match_date: null },
  ],
  updated_at: null,
  data_source: "dev_demo",
  disclaimer: "Demo data for local development only.",
};
