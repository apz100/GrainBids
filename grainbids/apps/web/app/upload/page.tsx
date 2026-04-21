import { redirect } from "next/navigation";

export default function LegacyUploadRoute() {
  redirect("/sources");
}
