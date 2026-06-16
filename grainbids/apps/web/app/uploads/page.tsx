import { redirect } from "next/navigation";

// Deprecated compatibility route. File uploads now live under the Sources admin surface.
export default function UploadsRoute() {
  redirect("/sources");
}
