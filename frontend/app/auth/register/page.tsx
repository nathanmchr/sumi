import { redirect } from "next/navigation";

export default function AuthRegisterRedirectPage() {
  redirect("/register");
}
