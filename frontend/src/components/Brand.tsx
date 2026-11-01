import { useAppName } from "../hooks/appInfo";

/** The dashboard's name with its last word highlighted, the way the headings have always shown it. */
export function Brand() {
  const name = useAppName();
  const words = name.split(" ");
  const last = words.pop() ?? "";
  return <>{words.length > 0 ? `${words.join(" ")} ` : ""}<span className="hl">{last}</span></>;
}
