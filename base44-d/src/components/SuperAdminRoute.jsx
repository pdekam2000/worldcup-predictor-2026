import React, { useState } from "react";

import { Navigate } from "react-router-dom";

import { useAuth } from "@/lib/AuthContext";

import { isSuperAdminUser, isOwnerUser } from "@/lib/roles";

import {

  fetchSuperAdminGateStatus,

  verifySuperAdminGate,

} from "@/lib/adminGate";

import AccessDenied from "@/components/AccessDenied";

import AdminGatePrompt from "@/components/AdminGatePrompt";



/** Super Admin route guard — super_admin role + second gate. Phase 37A */

export default function SuperAdminRoute({ children }) {

  const { isAuthenticated, user, isLoadingAuth } = useAuth();

  const [gatePassed, setGatePassed] = useState(false);



  if (isLoadingAuth) {

    return (

      <div className="flex justify-center py-20">

        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />

      </div>

    );

  }



  if (!isAuthenticated) {

    return <Navigate to="/login" replace />;

  }



  if (!isSuperAdminUser(user)) {

    return <AccessDenied />;

  }



  if (!gatePassed && !isOwnerUser(user)) {

    return (

      <AdminGatePrompt

        gate="super_admin"

        checkStatus={fetchSuperAdminGateStatus}

        verifyKey={verifySuperAdminGate}

        onVerified={() => setGatePassed(true)}

      />

    );

  }



  return children;

}

