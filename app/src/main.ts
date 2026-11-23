import { mount } from "svelte";
import App from "./App.svelte";
import { watchWindowScale } from "./lib/scale";
import "./styles/theme.css";

watchWindowScale();

export default mount(App, { target: document.getElementById("app")! });
