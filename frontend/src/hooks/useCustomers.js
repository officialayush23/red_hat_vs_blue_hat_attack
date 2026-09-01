import { useQuery } from "@tanstack/react-query";
import { getCaseEvidence, getCustomer, getCustomerCases, listCustomers } from "@/services/api/customers";

export function useCustomers() {
  return useQuery({ queryKey: ["customers"], queryFn: listCustomers, staleTime: 60_000 });
}

export function useCustomer(id) {
  return useQuery({ queryKey: ["customer", id], queryFn: () => getCustomer(id), enabled: !!id });
}

export function useCustomerCases(id, limit = 25) {
  return useQuery({
    queryKey: ["customer-cases", id, limit],
    queryFn: () => getCustomerCases(id, limit),
    enabled: !!id,
  });
}

export function useCaseEvidence(caseId) {
  return useQuery({
    queryKey: ["case-evidence", caseId],
    queryFn: () => getCaseEvidence(caseId),
    enabled: !!caseId,
  });
}
