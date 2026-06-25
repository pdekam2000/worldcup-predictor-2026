import React, { useEffect, useState } from "react";

import { Link } from "react-router-dom";

import { Mail, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";

import { useAuth } from "@/lib/AuthContext";

import { fetchAuthConfig } from "@/api/authApi";



/** Shown when logged-in user has not verified email — Phase 40A */

export default function EmailVerificationBanner() {

  const { user } = useAuth();

  const [verificationRequired, setVerificationRequired] = useState(true);



  useEffect(() => {

    fetchAuthConfig()

      .then((config) => setVerificationRequired(config?.email_verification_required !== false))

      .catch(() => setVerificationRequired(true));

  }, []);



  if (

    !verificationRequired ||

    !user ||

    user.email_verified ||

    user.role === "admin" ||

    user.role === "super_admin"

  ) {

    return null;

  }



  return (

    <div className="mb-4 glass rounded-xl p-4 border border-yellow-500/20 flex flex-col sm:flex-row sm:items-center gap-3">

      <div className="flex items-start gap-3 flex-1">

        <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />

        <div>

          <p className="font-medium text-sm">Email verification required</p>

          <p className="text-xs text-muted-foreground mt-1">

            Verify your email to unlock predictions. Settings and browsing remain available.

          </p>

        </div>

      </div>

      <Button asChild variant="outline" size="sm" className="flex-shrink-0">

        <Link to={`/verify-email?email=${encodeURIComponent(user.email || "")}`}>

          <Mail className="w-4 h-4 mr-2" />

          Verify email

        </Link>

      </Button>

    </div>

  );

}

