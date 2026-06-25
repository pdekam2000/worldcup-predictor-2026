import React, { useState } from "react";

import { Navigate } from "react-router-dom";

import { useAuth } from "@/lib/AuthContext";

import { isAdminUser, isOwnerUser } from "@/lib/roles";

import {

  fetchAdminGateStatus,

  verifyAdminGate,

} from "@/lib/adminGate";

import AccessDenied from "@/components/AccessDenied";

import AdminGatePrompt from "@/components/AdminGatePrompt";



/** Admin route guard — role + second-factor gate. Phase 37A */

export default function AdminRoute({ children }) {

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



  if (!isAdminUser(user)) {

    return <AccessDenied />;

  }



  if (!gatePassed && !isOwnerUser(user)) {

    return (

      <AdminGatePrompt

        gate="admin"

        checkStatus={fetchAdminGateStatus}

        verifyKey={verifyAdminGate}

        onVerified={() => setGatePassed(true)}

      />

    );

  }



  return children;

}

