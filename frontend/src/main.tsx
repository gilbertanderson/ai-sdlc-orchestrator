import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import DemoApp from "./demo/DemoApp";
import "./styles.css";

// `vite build --mode demo` builds the browser demo, which replays recorded runs with no server.
const Root = import.meta.env.MODE === "demo" ? DemoApp : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
