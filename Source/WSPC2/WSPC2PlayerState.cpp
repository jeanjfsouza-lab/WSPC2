#include "WSPC2PlayerState.h"
#include "Net/UnrealNetwork.h"

void AWSPC2PlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2PlayerState, Seat);
}
